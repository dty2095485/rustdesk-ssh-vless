#!/usr/bin/env python3
"""Stage/replace only Xray's executable; never change panel DB or client files."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import time
import uuid

import stage as shared
import promote as production

STATE = shared.STATE / "compat-core.json"
BIN = "/etc/x-ui/rustdesk-compat-core"
CONFIG = "/etc/x-ui/rustdesk-compat-config.json"
PID = "/etc/x-ui/rustdesk-compat.pid"
LOG = "/etc/x-ui/rustdesk-compat.log"
STAGED_BIN = "/app/bin/xray-rustdesk-compat-new"
BASE_IMAGE = "rustdesk-server-combined:reality-20260929"
COMPAT_IMAGE = "rustdesk-server-combined:tls-compat-20261002"
ENV_PATH = Path("/root/rustdesk-vless-stack-canary-20260929-1020/docker-combined/.env")


def persist(data):
    shared.save_json(STATE, data)


def load():
    if STATE.is_symlink() or not STATE.is_file():
        raise RuntimeError("compatibility manifest missing/unsafe")
    data = json.loads(STATE.read_text())
    mount, unused_identity = shared.data_mount()
    directory = Path(data["directory"])
    if directory.parent != shared.STATE or not directory.name.startswith("compat-core-") or directory.is_symlink():
        raise RuntimeError("unsafe backup directory")
    if str(mount) != data["mount"]:
        raise RuntimeError("container mount changed")
    return data, mount, directory


def binary_hash():
    output = shared.docker(["sha256sum", shared.XRAY]).stdout.decode("ascii")
    return output.split()[0]


def candidate_pid(mount):
    path = mount / Path(PID).name
    if path.is_symlink():
        raise RuntimeError("unsafe PID file")
    if not path.exists():
        return None
    value = path.read_text().strip()
    if not value.isdigit() or int(value) < 2:
        raise RuntimeError("invalid PID")
    result = shared.docker(["cat", "/proc/{}/cmdline".format(value)], check=False)
    if result.returncode:
        return None
    if result.stdout.split(b"\0")[:4] != [BIN.encode(), b"run", b"-c", CONFIG.encode()]:
        raise RuntimeError("candidate PID belongs to another process")
    return value


def stop_candidate(mount):
    pid = candidate_pid(mount)
    if pid:
        shared.docker(["kill", "-TERM", pid])
        for unused in range(50):
            if candidate_pid(mount) is None and not shared.port_open(18443):
                return
            time.sleep(0.1)
        raise RuntimeError("candidate did not exit")


def stage():
    if STATE.exists() or STATE.is_symlink():
        raise RuntimeError("compatibility manifest already exists")
    source = Path(__file__).resolve().parent / "xray-rustdesk-compat"
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("uploaded compatibility executable missing/unsafe")
    mount, identity = shared.data_mount()
    if shared.port_open(18443):
        raise RuntimeError("private candidate port busy")
    paths = [mount / Path(item).name for item in (BIN, CONFIG, PID, LOG)]
    if any(path.exists() or path.is_symlink() for path in paths):
        raise RuntimeError("candidate files already present")
    directory = shared.STATE / ("compat-core-" + time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700)
    # Capture the exact production executable outside the container for recovery.
    shared.command(["docker", "cp", shared.CONTAINER + ":" + shared.XRAY, str(directory / "original-xray")])
    os.chmod(str(directory / "original-xray"), 0o700)
    shutil.copyfile(str(source), str(paths[0]))
    os.chmod(str(paths[0]), 0o755)
    shared.save_json(paths[1], shared.candidate(identity), exclusive=True)
    production_data, unused_mount, unused_directory = production.load_manifest()
    data = {"status": "staging", "mount": str(mount), "directory": str(directory),
            "old_hash": binary_hash(), "new_hash": shared.digest(source),
            "runtime_hash": shared.docker(["sha256sum", "/app/bin/config.json"]).stdout.decode().split()[0]}
    if shared.digest(directory / "original-xray") != data["old_hash"]:
        raise RuntimeError("backup executable checksum mismatch")
    persist(data)
    result = shared.docker([BIN, "run", "-test", "-c", CONFIG], check=False)
    shared.write_exclusive(directory / "candidate-validation.log", result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("candidate configuration invalid")
    shared.command(["docker", "exec", "-d", shared.CONTAINER, "sh", "-c",
                    "echo $$ > " + PID + "; exec " + BIN + " run -c " + CONFIG + " > " + LOG + " 2>&1"])
    for unused in range(100):
        if candidate_pid(mount) and shared.port_open(18443):
            production.assert_guarded(production_data)
            data["status"] = "staged"
            persist(data)
            print("Private compatibility candidate ready on 127.0.0.1:18443; production core unchanged.")
            return
        time.sleep(0.1)
    raise RuntimeError("candidate failed to start")


def replace_core(data, mount, directory, restore=False):
    if restore and data.get("persisted_image"):
        if ENV_PATH.is_symlink() or shared.digest(ENV_PATH) != data["compose_env_after_hash"]:
            raise RuntimeError("Compose environment edited since image update; rollback refused")
        if shared.digest(directory / "compose-env-before") != data["compose_env_before_hash"]:
            raise RuntimeError("Compose environment backup checksum mismatch")
    expected = data["new_hash"] if restore else data["old_hash"]
    if binary_hash() != expected:
        raise RuntimeError("production executable changed concurrently; refusing overwrite")
    production_data, unused_mount, unused_directory = production.load_manifest()
    source = directory / "original-xray" if restore else mount / Path(BIN).name
    desired = data["old_hash"] if restore else data["new_hash"]
    if source.is_symlink() or shared.digest(source) != desired:
        raise RuntimeError("replacement checksum mismatch")
    # Validate the entire current panel-generated config with the replacement.
    shared.command(["docker", "cp", str(source), shared.CONTAINER + ":" + STAGED_BIN])
    shared.docker(["chmod", "755", STAGED_BIN])
    result = shared.docker([STAGED_BIN, "run", "-test", "-c", "/app/bin/config.json"], check=False)
    shared.write_exclusive(directory / ("rollback-validation.log" if restore else "production-validation.log"), result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("replacement rejected current production config")
    production.stop_ui(production_data)
    swapped = False
    try:
        shared.docker(["mv", STAGED_BIN, shared.XRAY])
        swapped = True
        production.start_ui(production_data, promoted=True)
        if binary_hash() != desired:
            raise RuntimeError("active executable checksum mismatch")
        current = shared.docker(["sha256sum", "/app/bin/config.json"]).stdout.decode().split()[0]
        if current != data["runtime_hash"]:
            raise RuntimeError("panel-generated runtime configuration changed")
    except Exception:
        if swapped and not restore:
            production.stop_ui(production_data)
            shared.command(["docker", "cp", str(directory / "original-xray"), shared.CONTAINER + ":" + STAGED_BIN])
            shared.docker(["chmod", "755", STAGED_BIN])
            shared.docker(["mv", STAGED_BIN, shared.XRAY])
        production.start_ui(production_data, promoted=True)
        raise
    if restore and data.get("persisted_image"):
        temporary = ENV_PATH.with_name(".env.rollback-" + uuid.uuid4().hex)
        shared.write_exclusive(temporary, (directory / "compose-env-before").read_bytes())
        os.replace(str(temporary), str(ENV_PATH))
    data["status"] = "rolled-back" if restore else "promoted"
    persist(data)
    stop_candidate(mount)
    print("Restored original Xray executable." if restore else "Replaced only Xray executable; panel config and RustDesk services unchanged.")


def persist_image(data, directory):
    if data["status"] != "promoted" or binary_hash() != data["new_hash"]:
        raise RuntimeError("compatibility core must be promoted before persisting image")
    if ENV_PATH.is_symlink() or not ENV_PATH.is_file():
        raise RuntimeError("unsafe Compose environment file")
    previous = ENV_PATH.read_bytes()
    old_line = ("IMAGE_TAG=" + BASE_IMAGE).encode()
    lines = previous.splitlines(keepends=True)
    if sum(line.rstrip(b"\r\n") == old_line for line in lines) != 1:
        raise RuntimeError("Compose image selection differs; refusing replacement")
    base = shared.command(["docker", "image", "inspect", "--format", "{{.Id}}", BASE_IMAGE]).stdout.decode().strip()
    if base != "sha256:385a969a2ae064169453d115dc6b1ae157ab419e9f545fb46170c4586508b721":
        raise RuntimeError("base image tag changed since compatibility validation")
    root = Path(__file__).resolve().parent
    result = shared.command(["docker", "build", "-f", str(root / "Dockerfile.compat"), "-t", COMPAT_IMAGE, str(root)], timeout=120, check=False)
    shared.write_exclusive(directory / "image-build.log", result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("compatibility image build failed; Compose not changed")
    check = shared.command(["docker", "run", "--rm", "--network", "none", "--entrypoint", "sha256sum", COMPAT_IMAGE, shared.XRAY]).stdout.decode().split()[0]
    if check != data["new_hash"]:
        raise RuntimeError("image executable checksum differs; Compose not changed")
    shared.write_exclusive(directory / "compose-env-before", previous)
    if ENV_PATH.read_bytes() != previous:
        raise RuntimeError("Compose environment changed concurrently")
    updated = b"".join((line.replace(old_line, ("IMAGE_TAG=" + COMPAT_IMAGE).encode(), 1)
                         if line.rstrip(b"\r\n") == old_line else line) for line in lines)
    temporary = ENV_PATH.with_name(".env.compat-" + uuid.uuid4().hex)
    shared.write_exclusive(temporary, updated)
    os.replace(str(temporary), str(ENV_PATH))
    data["persisted_image"] = COMPAT_IMAGE
    data["compose_env_before_hash"] = shared.digest(directory / "compose-env-before")
    data["compose_env_after_hash"] = shared.digest(ENV_PATH)
    persist(data)
    print("Compatibility image built and Compose IMAGE_TAG updated; running container not recreated.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["stage", "promote", "persist-image", "rollback", "status"])
    action = parser.parse_args().action
    if os.geteuid() != 0:
        raise RuntimeError("root required")
    os.umask(0o077)
    if shared.STATE.is_symlink():
        raise RuntimeError("unsafe state directory")
    shared.STATE.mkdir(mode=0o700, exist_ok=True)
    with (shared.STATE / ".compat-core.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if action == "stage":
            stage()
            return
        data, mount, directory = load()
        if action == "status":
            print(json.dumps({"status": data["status"], "core_hash": binary_hash(),
                              "candidate_running": candidate_pid(mount) is not None,
                              "listeners": {str(port): shared.port_open(port) for port in [10443,18444,18443]}}))
        elif action == "promote":
            if data["status"] != "staged":
                raise RuntimeError("no staged candidate")
            replace_core(data, mount, directory)
        elif action == "persist-image":
            persist_image(data, directory)
        else:
            if data["status"] != "promoted":
                raise RuntimeError("no promoted compatibility core")
            replace_core(data, mount, directory, restore=True)


if __name__ == "__main__":
    main()
