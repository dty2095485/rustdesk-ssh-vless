#!/usr/bin/env python3
"""Stage a private Xray TLS/fallback candidate; never change production :443.

Python 3.6+, root on VPS1. Copy this script and nginx-fallback.conf together.
    python3 stage.py stage
    python3 stage.py status
    python3 stage.py retire
    python3 stage.py rollback
All secrets stay in mode-0600 files. Existing Xray/x-ui DB/REALITY are untouched.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import uuid


CONTAINER = "rustdesk-server"
XRAY = "/app/bin/xray-linux-amd64"
CONFIG = "/etc/x-ui/rustdesk-tls-fallback-candidate.json"
PID = "/etc/x-ui/rustdesk-tls-fallback-candidate.pid"
LOG = "/etc/x-ui/rustdesk-tls-fallback-candidate.log"
ERROR_LOG = "/etc/x-ui/rustdesk-tls-fallback-candidate.error.log"
NGINX_CONF = Path("/www/server/panel/vhost/nginx/rustdesk-tls-fallback.conf")
STATE = Path("/var/lib/rustdesk-tls-fallback")
ACTIVE = STATE / "active.json"
MUX = Path("/www/server/panel/vhost/nginx/tcp/vless_mux.conf")
MUX_STATE = Path("/var/lib/rustdesk-mux-ui/state.json")
PORTS = (18443, 18081, 18082)
TAG = "rustdesk-tls-fallback-candidate"
EMAIL = "rustdesk-tls-client"


def command(argv, timeout=30, check=True):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout)
    if check and result.returncode:
        # Do not print raw tool output: config validation may contain credentials.
        raise RuntimeError("command failed: {} (exit {})".format(argv[0], result.returncode))
    return result


def docker(argv, **kwargs):
    return command(["docker", "exec", CONTAINER] + argv, **kwargs)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_exclusive(path, data):
    if path.is_symlink():
        raise RuntimeError("refusing symlink: {}".format(path))
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def save_json(path, data, exclusive=False):
    encoded = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if exclusive:
        write_exclusive(path, encoded)
    else:
        temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
        write_exclusive(temporary, encoded)
        os.replace(str(temporary), str(path))


def nginx_binary():
    preferred = Path("/www/server/nginx/sbin/nginx")
    binary = str(preferred) if preferred.is_file() else shutil.which("nginx")
    if not binary:
        raise RuntimeError("nginx binary not found")
    return binary


def nginx_reload(binary):
    command([binary, "-t"])
    command([binary, "-s", "reload"])


def data_mount():
    details = json.loads(command(["docker", "inspect", CONTAINER]).stdout.decode("utf-8"))[0]
    if not details.get("State", {}).get("Running"):
        raise RuntimeError("rustdesk-server is not running")
    if details.get("HostConfig", {}).get("NetworkMode") != "host":
        raise RuntimeError("candidate requires the current host-network container")
    matches = [item for item in details.get("Mounts", [])
               if item.get("Destination") == "/etc/x-ui" and item.get("Type") == "bind"]
    if len(matches) != 1 or not matches[0].get("RW"):
        raise RuntimeError("no unique writable /etc/x-ui bind mount")
    mount = Path(matches[0]["Source"])
    if not mount.is_absolute() or not mount.is_dir() or mount.is_symlink():
        raise RuntimeError("unsafe /etc/x-ui host mount")
    variables = dict(item.split("=", 1) for item in details.get("Config", {}).get("Env", [])
                     if "=" in item)
    identity = str(uuid.UUID(variables.get("VLESS_UUID", "")))
    return mount.resolve(), identity


def candidate(identity):
    outbounds = [{"tag": "blocked", "protocol": "blackhole", "settings": {}}]
    rules = []
    for logical in (21115, 21116, 21117):
        physical = logical + 1000
        target = "rustdesk-tls-{}".format(logical)
        outbounds.append({"tag": target, "protocol": "freedom", "settings": {
            "redirect": "127.0.0.1:{}".format(physical),
            "finalRules": [
                {"action": "allow", "network": "tcp", "ip": ["127.0.0.1"],
                 "port": str(physical)},
                {"action": "block"}
            ]
        }})
        rules.append({"type": "field", "inboundTag": [TAG], "user": [EMAIL],
                      "network": "tcp", "port": "21117,443,8443" if logical == 21117 else str(logical),
                      "outboundTag": target})
    rules.append({"type": "field", "inboundTag": [TAG], "outboundTag": "blocked"})
    return {
        "log": {"loglevel": "warning", "access": "none", "error": ERROR_LOG},
        "inbounds": [{
            "tag": TAG, "listen": "127.0.0.1", "port": 18443, "protocol": "vless",
            "settings": {"clients": [{"id": identity, "email": EMAIL, "flow": ""}],
                         "decryption": "none", "fallbacks": [
                             {"dest": "127.0.0.1:18081", "xver": 0},
                             {"alpn": "h2", "dest": "127.0.0.1:18082", "xver": 0}
                         ]},
            "streamSettings": {"network": "tcp", "security": "tls", "tlsSettings": {
                "alpn": ["h2", "http/1.1"], "minVersion": "1.2",
                "certificates": [{"certificateFile": "/run/tls/fullchain.pem",
                                  "keyFile": "/run/tls/privkey.pem"}]
            }}
        }],
        "outbounds": outbounds,
        "routing": {"domainStrategy": "AsIs", "rules": rules}
    }


def check_free_ports():
    for port in PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test:
            test.bind(("127.0.0.1", port))


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def wait_ports(expected, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(port_open(port) == expected for port in PORTS):
            return
        time.sleep(0.15)
    raise RuntimeError("candidate listeners did not reach expected state")


def backup_sqlite(source, destination):
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("x-ui database missing or unsafe")
    source_conn = sqlite3.connect("file:{}?mode=ro".format(source), uri=True, timeout=15)
    try:
        source_conn.execute("BEGIN")
        dump = "\n".join(source_conn.iterdump())
        target_conn = sqlite3.connect(str(destination))
        try:
            os.chmod(str(destination), 0o600)
            target_conn.executescript(dump)
            target_conn.commit()
            if target_conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("database backup failed integrity check")
        finally:
            target_conn.close()
    finally:
        source_conn.close()


def manifest_for(mount, directory):
    return {"version": 1, "container": CONTAINER, "mount": str(mount),
            "directory": str(directory), "status": "preparing", "owned": {},
            "nginx_binary": nginx_binary(), "config": CONFIG, "pid": PID,
            "production_mux_sha256": digest(MUX), "created_utc": datetime.datetime.utcnow().isoformat() + "Z"}


def load_manifest():
    if ACTIVE.is_symlink() or not ACTIVE.is_file():
        raise RuntimeError("no active candidate manifest")
    data = json.loads(ACTIVE.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data.get("container") != CONTAINER or data.get("config") != CONFIG or data.get("pid") != PID:
        raise RuntimeError("invalid candidate manifest")
    mount, unused_identity = data_mount()
    directory = Path(data.get("directory", ""))
    if str(mount) != data.get("mount") or directory.parent != STATE or directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("candidate paths do not match current container")
    if not directory.name.startswith("stage-"):
        raise RuntimeError("unexpected stage directory")
    if data.get("nginx_binary") != nginx_binary():
        raise RuntimeError("nginx binary does not match candidate manifest")
    allowed = {str(mount / Path(CONFIG).name), str(NGINX_CONF)}
    if set(data.get("owned", {})) - allowed:
        raise RuntimeError("manifest contains unexpected owned files")
    return data, mount, directory


def candidate_pid(mount):
    path = mount / Path(PID).name
    if not path.exists():
        return None
    if path.is_symlink():
        raise RuntimeError("candidate pid file is a symlink")
    value = path.read_text(encoding="ascii").strip()
    if not value.isdigit() or int(value) <= 1:
        raise RuntimeError("invalid candidate pid")
    response = docker(["cat", "/proc/{}/cmdline".format(value)], check=False)
    if response.returncode or not response.stdout:
        return None
    args = response.stdout.split(b"\0")
    expected = [XRAY.encode("ascii"), b"run", b"-c", CONFIG.encode("ascii")]
    if args[:4] != expected:
        raise RuntimeError("pid belongs to another process; refusing to stop it")
    return value


def retire(data, mount, directory):
    """Retire only the standalone test Xray after production and mux succeed.

    A durable retiring record makes every step retryable. Shared HTTP fallback
    listeners and their owned Nginx configuration remain in place.
    """
    production_path = STATE / "production.json"
    mux_path = STATE / "mux-switch.json"
    for path in (production_path, mux_path):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("required production/mux manifest missing or unsafe")
    production = json.loads(production_path.read_text(encoding="utf-8"))
    mux = json.loads(mux_path.read_text(encoding="utf-8"))
    production_directory = Path(production.get("directory", ""))
    if production.get("status") != "prepared" or mux.get("status") != "applied":
        raise RuntimeError("retire requires prepared production and applied public mux")
    if production.get("mount") != str(mount) or production.get("tag") != "in-18444-tcp" or production.get("port") != 18444:
        raise RuntimeError("production endpoint does not match this candidate")
    if production_directory.parent != STATE or not production_directory.name.startswith("production-") or production_directory.is_symlink() or not production_directory.is_dir():
        raise RuntimeError("unsafe production backup directory")
    production_backup = production_directory / "manifest.json"
    if production_backup.is_symlink():
        raise RuntimeError("unsafe production backup manifest")
    if not all(port_open(port) for port in (18444, 18081, 18082)):
        raise RuntimeError("production TLS and shared fallbacks must be healthy before retirement")
    if data.get("status") not in ("staged", "retiring", "retired"):
        raise RuntimeError("candidate cannot retire from its current state")

    config_source = mount / Path(CONFIG).name
    sources = (config_source, mount / Path(LOG).name, mount / Path(ERROR_LOG).name)
    record = data.get("retirement", {})
    archive = record.get("files", {})
    allowed_sources = {str(path) for path in sources}
    if set(archive) - allowed_sources:
        raise RuntimeError("retirement contains unexpected archive paths")
    for name, entry in archive.items():
        if entry.get("backup") != str(directory / Path(name).name):
            raise RuntimeError("retirement contains unsafe archive destinations")
    for name, expected in data.get("owned", {}).items():
        path = Path(name)
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_file() or digest(path) != expected:
                raise RuntimeError("owned candidate file changed; refusing retirement")
        elif name == str(config_source) and name in archive:
            saved = Path(archive[name]["backup"])
            if saved.is_symlink() or not saved.is_file() or digest(saved) != expected:
                raise RuntimeError("archived candidate config hash mismatch")
        else:
            raise RuntimeError("owned candidate file missing; refusing retirement")
    if str(NGINX_CONF) not in data.get("owned", {}):
        raise RuntimeError("shared Nginx fallback ownership is missing")
    for source in sources:
        destination = directory / source.name
        if source.is_symlink() or destination.is_symlink():
            raise RuntimeError("candidate archive path became a symlink")
        if source.exists() and (not source.is_file() or destination.exists()):
            raise RuntimeError("refusing to overwrite a candidate archive")

    pid = candidate_pid(mount)
    if data.get("status") == "retired":
        if pid is not None or production.get("candidate_pid") is not None or port_open(18443):
            raise RuntimeError("retired candidate unexpectedly still running")
        print("Standalone candidate already retired; production and shared fallbacks remain active.")
        return
    original_pid = record.get("candidate_pid", production.get("candidate_pid"))
    if original_pid is None or (pid is not None and str(pid) != str(original_pid)):
        raise RuntimeError("production candidate ownership differs from the test process")
    if production.get("candidate_pid") not in (original_pid, None):
        raise RuntimeError("production candidate ownership changed during retirement")
    pid_path = mount / Path(PID).name
    if pid_path.is_symlink():
        raise RuntimeError("candidate pid file is unsafe")
    if pid_path.exists() and pid_path.read_text(encoding="ascii").strip() != str(original_pid):
        raise RuntimeError("candidate pid file changed; refusing retirement")

    record.update({"candidate_pid": original_pid, "production_directory": str(production_directory), "files": archive})
    data["retirement"] = record
    data["status"] = "retiring"
    save_json(ACTIVE, data)
    save_json(directory / "manifest.json", data)
    if pid:
        docker(["kill", "-TERM", pid])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and (candidate_pid(mount) is not None or port_open(18443)):
        time.sleep(0.1)
    if candidate_pid(mount) is not None or port_open(18443):
        raise RuntimeError("candidate did not stop; retirement record preserved for retry")
    if not all(port_open(port) for port in (18444, 18081, 18082)):
        raise RuntimeError("production health changed; retirement record preserved")

    # Update both production manifests immediately after confirmed process exit,
    # so its future guarded rollback expects no standalone candidate process.
    production["candidate_pid"] = None
    production["candidate_retired_utc"] = datetime.datetime.utcnow().isoformat() + "Z"
    save_json(production_path, production)
    save_json(production_backup, production)
    for source in sources:
        name = str(source)
        destination = directory / source.name
        if name not in archive and source.exists():
            archive[name] = {"backup": str(destination), "sha256": digest(source)}
            save_json(ACTIVE, data)
            save_json(directory / "manifest.json", data)
        if name not in archive:
            continue
        expected = archive[name]["sha256"]
        if source.exists():
            if source.is_symlink() or digest(source) != expected or destination.exists() or destination.is_symlink():
                raise RuntimeError("candidate archive changed during retirement")
            os.replace(str(source), str(destination))
        if destination.is_symlink() or not destination.is_file() or digest(destination) != expected:
            raise RuntimeError("candidate archive hash verification failed")
    if pid_path.exists():
        if pid_path.is_symlink() or pid_path.read_text(encoding="ascii").strip() != str(original_pid):
            raise RuntimeError("candidate pid file changed before removal")
        pid_path.unlink()
    data["owned"].pop(str(config_source), None)
    data["status"] = "retired"
    data["retired_utc"] = datetime.datetime.utcnow().isoformat() + "Z"
    save_json(ACTIVE, data)
    save_json(directory / "manifest.json", data)
    print("Standalone candidate retired. Its config/logs are archived; production Xray and shared Nginx fallbacks remain active.")


def rollback(data, mount, directory):
    production = STATE / "production.json"
    if production.exists() or production.is_symlink():
        if production.is_symlink():
            raise RuntimeError("unsafe production manifest; refusing shared fallback removal")
        deployed = json.loads(production.read_text(encoding="utf-8"))
        if deployed.get("status") not in ("rolled-back", "not-applied"):
            raise RuntimeError("production TLS uses shared fallback backends; rollback production first")
    # Validate all hashes before any removal, so a changed file is preserved.
    for name, expected in data.get("owned", {}).items():
        path = Path(name)
        if path.exists() and (path.is_symlink() or digest(path) != expected):
            raise RuntimeError("owned file changed; refusing automatic rollback: {}".format(name))
    pid = candidate_pid(mount)
    if pid:
        docker(["kill", "-TERM", pid])
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and candidate_pid(mount):
            time.sleep(0.1)
        if candidate_pid(mount):
            raise RuntimeError("candidate did not stop; leaving configuration in place")
    for name in data.get("owned", {}):
        path = Path(name)
        if path.exists():
            path.unlink()
    nginx_reload(data["nginx_binary"])
    pid_path = mount / Path(PID).name
    if pid_path.exists() and not pid_path.is_symlink():
        pid_path.unlink()
    # Preserve diagnostic output, and clear only the two exact candidate log
    # paths which were required not to exist before staging. Never recurse.
    for container_path in (LOG, ERROR_LOG):
        source = mount / Path(container_path).name
        destination = directory / source.name
        if source.is_symlink():
            raise RuntimeError("candidate log became a symlink; preserving it")
        if source.exists():
            if not source.is_file() or destination.exists() or destination.is_symlink():
                raise RuntimeError("cannot safely archive candidate diagnostic log")
            os.replace(str(source), str(destination))
    data["status"] = "rolled-back"
    data["rolled_back_utc"] = datetime.datetime.utcnow().isoformat() + "Z"
    save_json(directory / "manifest.json", data)
    if ACTIVE.exists():
        ACTIVE.unlink()
    print("Rolled back only the private candidate. Production :443, x-ui DB and REALITY were not modified.")


def stage():
    if ACTIVE.exists() or ACTIVE.is_symlink():
        raise RuntimeError("candidate already tracked; use status or rollback")
    mount, identity = data_mount()
    host_config = mount / Path(CONFIG).name
    for path in (host_config, NGINX_CONF, mount / Path(PID).name,
                 mount / Path(LOG).name, mount / Path(ERROR_LOG).name):
        if path.exists() or path.is_symlink():
            raise RuntimeError("refusing to overwrite existing candidate artifact: {}".format(path))
    check_free_ports()
    for port in (4443, 22115, 22116, 22117):
        if not port_open(port):
            raise RuntimeError("required local backend {} is not listening".format(port))
    directory = STATE / ("stage-" + datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700)
    data = manifest_for(mount, directory)
    backup_sqlite(mount / "x-ui.db", directory / "x-ui.db")
    runtime = docker(["cat", "/app/bin/config.json"]).stdout
    write_exclusive(directory / "runtime-config.json", runtime)
    for source, name in ((MUX, "production-vless_mux.conf"), (MUX_STATE, "production-mux-state.json")):
        write_exclusive(directory / name, source.read_bytes())
    save_json(directory / "manifest.json", data, exclusive=True)
    save_json(ACTIVE, data, exclusive=True)
    try:
        save_json(host_config, candidate(identity), exclusive=True)
        data["owned"][str(host_config)] = digest(host_config)
        save_json(ACTIVE, data)
        docker([XRAY, "run", "-test", "-c", CONFIG])
        template = Path(__file__).resolve().parent / "nginx-fallback.conf"
        write_exclusive(NGINX_CONF, template.read_bytes())
        data["owned"][str(NGINX_CONF)] = digest(NGINX_CONF)
        save_json(ACTIVE, data)
        nginx_reload(data["nginx_binary"])
        shell = "umask 077; echo $$ > {pid}; exec {xray} run -c {config} >> {log} 2>&1".format(
            pid=shlex.quote(PID), xray=shlex.quote(XRAY), config=shlex.quote(CONFIG), log=shlex.quote(LOG))
        command(["docker", "exec", "-d", CONTAINER, "sh", "-c", shell])
        wait_ports(True)
        if candidate_pid(mount) is None:
            raise RuntimeError("candidate process ownership not confirmed")
        if digest(MUX) != data["production_mux_sha256"]:
            raise RuntimeError("production mux changed concurrently; candidate not accepted")
        data["status"] = "staged"
        save_json(ACTIVE, data)
        save_json(directory / "manifest.json", data)
        print("Private candidate ready on 127.0.0.1:18443; fallback backends 18081/18082.")
        print("Backup directory: {}".format(directory))
        print("Production :443, existing Xray process, x-ui DB and REALITY were not modified.")
    except Exception:
        try:
            rollback(data, mount, directory)
        except Exception as cleanup_error:
            print("Automatic rollback needs attention: {}".format(cleanup_error), file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "status", "retire", "rollback"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError("run as root on VPS1")
    os.umask(0o077)
    if STATE.is_symlink():
        raise RuntimeError("state directory cannot be a symlink")
    STATE.mkdir(mode=0o700, exist_ok=True)
    os.chmod(str(STATE), 0o700)
    lock_fd = os.open(str(STATE / ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "stage":
            stage()
        else:
            data, mount, directory = load_manifest()
            if args.action == "rollback":
                rollback(data, mount, directory)
            elif args.action == "retire":
                retire(data, mount, directory)
            else:
                print(json.dumps({"status": data["status"], "backup_directory": str(directory),
                                  "candidate_pid_confirmed": candidate_pid(mount) is not None,
                                  "listeners": {str(port): port_open(port) for port in PORTS},
                                  "production_mux_unchanged": digest(MUX) == data["production_mux_sha256"]}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        sys.exit(1)
