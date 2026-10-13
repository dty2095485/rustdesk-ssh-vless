#!/usr/bin/env python3
"""Add a private, UI-managed TLS inbound to VPS1's existing 3x-ui Xray.

    python3 promote.py prepare
    python3 promote.py status
    python3 promote.py rollback

Does NOT change the public mux. Stop/start only s6 reality-ui, not RustDesk
services or the standalone candidate. Python 3.6, stdlib; stage.py is required.
"""
import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import sys
import time
import uuid

import stage as shared


MANIFEST = shared.STATE / "production.json"
SERVICE = "/run/service/reality-ui"
SVC = "/command/s6-svc"
STAT = "/command/s6-svstat"
TAG = "in-18444-tcp"
PORT = 18444
EMAIL = shared.EMAIL
VALIDATION = "/etc/x-ui/rustdesk-tls-fallback-production-check.json"
GUARDED_SERVICES = ("hbbs", "hbbr", "hbvless", "hbssh")
TABLES = ("inbounds", "clients", "client_inbounds", "client_traffics", "settings")


def read_runtime():
    return json.loads(shared.docker(["cat", "/app/bin/config.json"]).stdout.decode("utf-8"))


def service_pid(name):
    result = shared.docker([STAT, "/run/service/" + name]).stdout.decode("ascii")
    match = re.match(r"up \(pid (\d+)(?: |\))", result)
    return int(match.group(1)) if match else None


def assert_guarded(data):
    for name, expected in data["service_pids"].items():
        if service_pid(name) != expected:
            raise RuntimeError("unrelated service {} changed process; refusing to continue".format(name))
    if shared.candidate_pid(Path(data["mount"])) != data["candidate_pid"]:
        raise RuntimeError("standalone candidate process changed")


def database(path):
    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def rows(conn, table):
    return [dict(row) for row in conn.execute("SELECT * FROM " + table)]


def template_row(conn):
    found = conn.execute("SELECT id,value FROM settings WHERE key=?", ("xrayTemplateConfig",)).fetchall()
    if len(found) != 1:
        raise RuntimeError("expected exactly one xrayTemplateConfig row")
    return int(found[0]["id"]), found[0]["value"]


def validate_schema(conn):
    required = {
        "inbounds": {"id", "user_id", "listen", "port", "protocol", "settings", "stream_settings", "tag", "sniffing"},
        "clients": {"id", "email", "uuid", "flow", "enable", "created_at", "updated_at"},
        "client_inbounds": {"client_id", "inbound_id", "flow_override", "created_at"},
        "client_traffics": {"id", "inbound_id", "email", "enable", "up", "down"},
        "settings": {"id", "key", "value"},
    }
    for table, columns in required.items():
        actual = {item[1] for item in conn.execute("PRAGMA table_info(" + table + ")")}
        if not columns.issubset(actual):
            raise RuntimeError("unsupported 3x-ui schema: " + table)


def insert(conn, table, values):
    keys = sorted(values)
    query = "INSERT INTO {} ({}) VALUES ({})".format(table, ",".join(keys), ",".join("?" for key in keys))
    return int(conn.execute(query, [values[key] for key in keys]).lastrowid)


def additions(identity):
    source = shared.candidate(identity)
    inbound = copy.deepcopy(source["inbounds"][0])
    inbound["tag"] = TAG
    inbound["port"] = PORT
    inbound["streamSettings"]["tcpSettings"] = {"acceptProxyProtocol": False, "header": {"type": "none"}}
    inbound["sniffing"] = {"enabled": False}
    outbounds = copy.deepcopy(source["outbounds"][1:])
    rules = copy.deepcopy(source["routing"]["rules"])
    for rule in rules:
        rule["inboundTag"] = [TAG]
    return inbound, outbounds, rules


def add_to_config(original, inbound, outbounds, rules, include_inbound):
    result = copy.deepcopy(original)
    present = {item.get("tag") for item in result.get("outbounds", [])}
    if present & {item["tag"] for item in outbounds}:
        raise RuntimeError("TLS outbound tags already exist")
    if any(item.get("tag") == TAG or item.get("port") == PORT for item in result.get("inbounds", [])):
        raise RuntimeError("TLS inbound tag or port already exists")
    if include_inbound:
        result.setdefault("inbounds", []).append(inbound)
    result.setdefault("outbounds", []).extend(outbounds)
    current = result.setdefault("routing", {}).setdefault("rules", [])
    # Keep the API rule first; insert before private-range and user catch-all rules.
    position = 1 if current and current[0].get("inboundTag") == ["api"] else 0
    current[position:position] = rules
    return result


def check_runtime_config(mount, config, directory):
    destination = mount / Path(VALIDATION).name
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("existing production validation file; refusing overwrite")
    shared.save_json(destination, config, exclusive=True)
    expected = shared.digest(destination)
    try:
        result = shared.docker([shared.XRAY, "run", "-test", "-c", VALIDATION], check=False)
        shared.write_exclusive(directory / "xray-validation-output.log", result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("full prospective Xray config failed validation (protected log retained)")
    finally:
        if destination.is_file() and not destination.is_symlink() and shared.digest(destination) == expected:
            destination.unlink()


def snapshot(conn):
    return {name: rows(conn, name) for name in TABLES}


def immutable_snapshot(before, after, data):
    for name in TABLES:
        previous = before[name]
        current = after[name]
        if name == "inbounds":
            current = [item for item in current if item["id"] != data["inbound_id"]]
            ignored = {"up", "down", "last_traffic_reset_time"}
        elif name == "clients":
            current = [item for item in current if item["id"] != data["client_id"]]
            ignored = set()
        elif name == "client_inbounds":
            current = [item for item in current if not (item["inbound_id"] == data["inbound_id"] and item["client_id"] == data["client_id"])]
            ignored = set()
        elif name == "client_traffics":
            current = [item for item in current if item["id"] != data["traffic_id"]]
            ignored = {"up", "down", "last_online", "last_sub_fetch"}
        else:
            previous = [item for item in previous if item["id"] != data["template_id"]]
            current = [item for item in current if item["id"] != data["template_id"]]
            ignored = set()
        normalize = lambda items: sorted([{key: value for key, value in item.items() if key not in ignored} for item in items], key=lambda item: json.dumps(item, sort_keys=True))
        if normalize(previous) != normalize(current):
            raise RuntimeError("pre-existing {} configuration changed".format(name))


def owned_main_xray(pid):
    response = shared.docker(["cat", "/proc/{}/cmdline".format(pid)], check=False)
    if response.returncode or not response.stdout:
        return False
    parts = response.stdout.split(b"\0")
    if parts[:3] not in ([b"bin/xray-linux-amd64", b"-c", b"bin/config.json"],
                         [shared.XRAY.encode("ascii"), b"-c", b"/app/bin/config.json"]):
        raise RuntimeError("main Xray PID now belongs to another process")
    return True


def main_xray_pid(required=True):
    parent = service_pid("reality-ui")
    if not parent and required:
        raise RuntimeError("x-ui service not up")
    if not parent:
        return None
    listing = shared.docker(["ps", "-o", "pid,ppid,args"]).stdout.decode("utf-8")
    matches = []
    for line in listing.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[1].isdigit() and int(parts[1]) == parent and "xray-linux-amd64" in parts[2]:
            pid = int(parts[0])
            if owned_main_xray(pid):
                matches.append(pid)
    if not matches and not required:
        return None
    if len(matches) != 1:
        raise RuntimeError("expected one owned main Xray child")
    return matches[0]


def stop_ui(data):
    pid = main_xray_pid(required=False)
    shared.docker([SVC, "-d", "-wD", "-T", "15000", SERVICE], timeout=20)
    # x-ui normally stops its Xray child. If it leaves that exact child behind,
    # terminate only the pre-checked production config process, never candidate.
    if pid is not None and owned_main_xray(pid):
        shared.docker(["kill", "-TERM", str(pid)])
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if service_pid("reality-ui") is None and not shared.port_open(2053) and not shared.port_open(10443) and not shared.port_open(PORT):
            assert_guarded(data)
            return
        time.sleep(0.15)
    raise RuntimeError("x-ui / main Xray did not stop safely")


def start_ui(data, promoted):
    shared.docker([SVC, "-u", SERVICE])
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if service_pid("reality-ui") and shared.port_open(2053) and shared.port_open(10443) and (shared.port_open(PORT) if promoted else not shared.port_open(PORT)):
            assert_guarded(data)
            return
        time.sleep(0.2)
    raise RuntimeError("x-ui / REALITY / TLS listeners not healthy after restart")


def verify_runtime(baseline, actual, data):
    stripped = copy.deepcopy(actual)
    new_inbounds = [item for item in stripped.get("inbounds", []) if item.get("tag") == TAG]
    if len(new_inbounds) != 1:
        raise RuntimeError("expected one production TLS inbound in generated runtime")
    new = new_inbounds[0]
    if new.get("listen") != "127.0.0.1" or new.get("port") != PORT or new.get("protocol") != "vless":
        raise RuntimeError("unexpected production inbound endpoint")
    settings = new.get("settings", {})
    clients = settings.get("clients", [])
    if len(clients) != 1 or clients[0].get("id") != data["identity"] or clients[0].get("email") != EMAIL or clients[0].get("flow", ""):
        raise RuntimeError("production TLS client identity/flow mismatch")
    expected = data["new_inbound"]
    if settings.get("decryption") != "none" or settings.get("fallbacks") != expected["settings"]["fallbacks"]:
        raise RuntimeError("production fallback settings mismatch")
    stream = new.get("streamSettings", {})
    if stream.get("security") != "tls" or stream.get("network") not in ("tcp", "raw"):
        raise RuntimeError("production TLS transport mismatch")
    tls = stream.get("tlsSettings", {})
    if tls.get("alpn") != ["h2", "http/1.1"] or tls.get("certificates") != expected["streamSettings"]["tlsSettings"]["certificates"]:
        raise RuntimeError("production TLS ALPN/certificate mismatch")
    stripped["inbounds"] = [item for item in stripped.get("inbounds", []) if item.get("tag") != TAG]
    tags = {item["tag"] for item in data["new_outbounds"]}
    real_outbounds = [item for item in stripped.get("outbounds", []) if item.get("tag") in tags]
    if real_outbounds != data["new_outbounds"]:
        raise RuntimeError("production fixed redirect outbound mismatch")
    stripped["outbounds"] = [item for item in stripped["outbounds"] if item.get("tag") not in tags]
    real_rules = [item for item in stripped.get("routing", {}).get("rules", []) if item.get("inboundTag") == [TAG]]
    if real_rules != data["new_rules"]:
        raise RuntimeError("production inbound routing mismatch")
    stripped["routing"]["rules"] = [item for item in stripped["routing"]["rules"] if item.get("inboundTag") != [TAG]]
    if stripped != baseline:
        raise RuntimeError("pre-existing generated runtime changed; refusing production promotion")


def load_manifest():
    if MANIFEST.is_symlink() or not MANIFEST.is_file():
        raise RuntimeError("production manifest missing or unsafe")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    mount, identity = shared.data_mount()
    directory = Path(data.get("directory", ""))
    if data.get("version") != 1 or data.get("tag") != TAG or data.get("port") != PORT or data.get("mount") != str(mount) or data.get("identity") != identity:
        raise RuntimeError("production manifest does not match current deployment")
    if directory.parent != shared.STATE or not directory.name.startswith("production-") or directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("unsafe production backup directory")
    return data, mount, directory


def remove_owned_changes(data, mount):
    conn = database(mount / "x-ui.db")
    try:
        conn.execute("BEGIN IMMEDIATE")
        template_id, current = template_row(conn)
        if template_id != data["template_id"] or current not in (data["template_before"], data["template_after"]):
            raise RuntimeError("panel template changed after promotion; automatic rollback refused")
        new = conn.execute("SELECT tag,port FROM inbounds WHERE id=?", (data["inbound_id"],)).fetchone()
        if new and (new["tag"] != TAG or new["port"] != PORT):
            raise RuntimeError("owned inbound ID reused; rollback refused")
        client = conn.execute("SELECT email,uuid FROM clients WHERE id=?", (data["client_id"],)).fetchone()
        if client and (client["email"] != EMAIL or client["uuid"] != data["identity"]):
            raise RuntimeError("owned client ID reused; rollback refused")
        extra = conn.execute("SELECT inbound_id FROM client_inbounds WHERE client_id=? AND inbound_id<>?", (data["client_id"], data["inbound_id"])).fetchone()
        if extra:
            raise RuntimeError("TLS client is now shared by another inbound; rollback refused")
        extra = conn.execute("SELECT client_id FROM client_inbounds WHERE inbound_id=? AND client_id<>?", (data["inbound_id"], data["client_id"])).fetchone()
        if extra:
            raise RuntimeError("TLS inbound now has another client's configuration; rollback refused")
        traffic = conn.execute("SELECT email,inbound_id FROM client_traffics WHERE id=?", (data["traffic_id"],)).fetchone()
        if traffic and (traffic["email"] != EMAIL or traffic["inbound_id"] != data["inbound_id"]):
            raise RuntimeError("owned traffic ID reused; rollback refused")
        conn.execute("DELETE FROM client_inbounds WHERE client_id=? AND inbound_id=?", (data["client_id"], data["inbound_id"]))
        conn.execute("DELETE FROM client_traffics WHERE id=?", (data["traffic_id"],))
        conn.execute("DELETE FROM inbounds WHERE id=?", (data["inbound_id"],))
        conn.execute("DELETE FROM clients WHERE id=?", (data["client_id"],))
        conn.execute("UPDATE settings SET value=? WHERE id=?", (data["template_before"], data["template_id"]))
        conn.commit()
    finally:
        conn.close()


def rollback(data, mount, directory, already_stopped=False):
    # If the mux has switched, its owning script must restore it first.
    mux_state = shared.STATE / "mux-switch.json"
    if mux_state.exists() or mux_state.is_symlink():
        if mux_state.is_symlink():
            raise RuntimeError("unsafe mux-switch manifest")
        mux = json.loads(mux_state.read_text(encoding="utf-8"))
        if mux.get("status") not in ("rolled-back", "not-applied"):
            raise RuntimeError("restore public mux before removing the production TLS inbound")
    if data.get("status") == "rolled-back":
        print("Production TLS already rolled back.")
        return
    if not already_stopped:
        stop_ui(data)
    try:
        if data.get("database_applied"):
            remove_owned_changes(data, mount)
    except Exception:
        start_ui(data, promoted=bool(data.get("database_applied")))
        raise
    start_ui(data, promoted=False)
    data["status"] = "rolled-back"
    shared.save_json(MANIFEST, data)
    shared.save_json(directory / "manifest.json", data)
    print("Only production TLS DB additions removed; existing clients/counters and shared fallback backends preserved.")


def prepare():
    if MANIFEST.exists() or MANIFEST.is_symlink():
        raise RuntimeError("production manifest already exists; inspect or rollback first")
    candidate_data, mount, unused_stage_dir = shared.load_manifest()
    if candidate_data.get("status") != "staged" or not all(shared.port_open(port) for port in shared.PORTS):
        raise RuntimeError("validated private candidate and fallback backends must be running")
    unused_mount, identity = shared.data_mount()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test:
        test.bind(("127.0.0.1", PORT))
    directory = shared.STATE / ("production-" + time.strftime("%Y%m%d-%H%M%S-", time.gmtime()) + uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700)
    inbound, outbounds, rules = additions(identity)
    baseline_runtime = read_runtime()
    conn = database(mount / "x-ui.db")
    try:
        validate_schema(conn)
        template_id, template_before = template_row(conn)
        if conn.execute("SELECT id FROM inbounds WHERE port=? OR tag=?", (PORT, TAG)).fetchone() or conn.execute("SELECT id FROM clients WHERE email=?", (EMAIL,)).fetchone() or conn.execute("SELECT id FROM client_traffics WHERE email=?", (EMAIL,)).fetchone():
            raise RuntimeError("production TLS inbound/client already exists")
        template_after = json.dumps(add_to_config(json.loads(template_before), inbound, outbounds, rules, False), separators=(",", ":"))
    finally:
        conn.close()
    check_runtime_config(mount, add_to_config(baseline_runtime, inbound, outbounds, rules, True), directory)
    data = {"version": 1, "status": "preparing", "tag": TAG, "port": PORT, "mount": str(mount),
            "directory": str(directory), "identity": identity, "template_id": template_id,
            "template_before": template_before, "template_after": template_after,
            "new_inbound": inbound, "new_outbounds": outbounds, "new_rules": rules,
            "service_pids": {name: service_pid(name) for name in GUARDED_SERVICES},
            "candidate_pid": shared.candidate_pid(mount), "database_applied": False}
    if any(value is None for value in data["service_pids"].values()) or data["candidate_pid"] is None:
        raise RuntimeError("all existing RustDesk services and candidate must be healthy")
    shared.save_json(MANIFEST, data, exclusive=True)
    stopped = False
    try:
        stop_ui(data)
        stopped = True
        if read_runtime() != baseline_runtime:
            raise RuntimeError("runtime changed concurrently before service stop")
        shared.backup_sqlite(mount / "x-ui.db", directory / "x-ui.db")
        shared.save_json(directory / "runtime-before.json", baseline_runtime, exclusive=True)
        conn = database(mount / "x-ui.db")
        try:
            conn.execute("BEGIN IMMEDIATE")
            actual_template_id, actual_template = template_row(conn)
            if actual_template_id != template_id or actual_template != template_before:
                raise RuntimeError("DB template changed concurrently before service stop")
            before = snapshot(conn)
            owner = conn.execute("SELECT user_id FROM inbounds ORDER BY id LIMIT 1").fetchone()
            if not owner:
                raise RuntimeError("existing inbound owner missing")
            now = int(time.time() * 1000)
            client_settings = {"id": identity, "email": EMAIL, "flow": "", "enable": True,
                               "limitIp": 0, "totalGB": 0, "expiryTime": 0, "tgId": 0,
                               "reset": 0, "comment": "RustDesk TLS transport only",
                               "created_at": now, "updated_at": now, "subId": uuid.uuid4().hex[:16]}
            settings = copy.deepcopy(inbound["settings"])
            settings["clients"] = [client_settings]
            settings["encryption"] = "none"
            data["inbound_id"] = insert(conn, "inbounds", {
                "user_id": owner["user_id"], "up": 0, "down": 0, "total": 0,
                "remark": "RustDesk TLS fallback - NAS :443", "enable": 1, "expiry_time": 0,
                "listen": "127.0.0.1", "port": PORT, "protocol": "vless", "tag": TAG,
                "settings": json.dumps(settings), "stream_settings": json.dumps(inbound["streamSettings"]),
                "sniffing": json.dumps(inbound["sniffing"]), "share_addr_strategy": "listen", "share_addr": "",
            })
            data["client_id"] = insert(conn, "clients", {
                "email": EMAIL, "uuid": identity, "sub_id": client_settings["subId"], "flow": "",
                "security": "auto", "enable": 1, "limit_ip": 0, "total_gb": 0,
                "expiry_time": 0, "tg_id": 0, "comment": client_settings["comment"],
                "created_at": now, "updated_at": now,
            })
            insert(conn, "client_inbounds", {"client_id": data["client_id"], "inbound_id": data["inbound_id"],
                                            "flow_override": "", "created_at": now})
            data["traffic_id"] = insert(conn, "client_traffics", {"inbound_id": data["inbound_id"], "enable": 1,
                                                               "email": EMAIL, "up": 0, "down": 0, "expiry_time": 0, "total": 0})
            conn.execute("UPDATE settings SET value=? WHERE id=?", (template_after, template_id))
            immutable_snapshot(before, snapshot(conn), data)
            shared.save_json(directory / "db-config-before.json", before, exclusive=True)
            data["database_applied"] = True
            data["status"] = "database-applied"
            shared.save_json(MANIFEST, data)
            conn.commit()
        finally:
            conn.close()
        stopped = False
        start_ui(data, promoted=True)
        verify_runtime(baseline_runtime, read_runtime(), data)
        conn = database(mount / "x-ui.db")
        try:
            immutable_snapshot(before, snapshot(conn), data)
        finally:
            conn.close()
        data["status"] = "prepared"
        shared.save_json(MANIFEST, data)
        shared.save_json(directory / "manifest.json", data)
        print("UI-managed production TLS inbound ready privately on 127.0.0.1:18444.")
        print("Existing REALITY and proxy rules preserved. Public mux unchanged; verify before switching ALPN rule.")
        print("Protected backup directory: {}".format(directory))
    except Exception:
        try:
            # If stop failed after downing x-ui, first restore service health.
            if not stopped and service_pid("reality-ui") is None:
                start_ui(data, promoted=bool(data.get("database_applied")))
            rollback(data, mount, directory, already_stopped=stopped)
        except Exception as error:
            print("Automatic production rollback needs attention: {}".format(error), file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "status", "rollback"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError("run as root on VPS1")
    os.umask(0o077)
    if not shared.STATE.is_dir() or shared.STATE.is_symlink():
        raise RuntimeError("candidate state directory missing or unsafe")
    fd = os.open(str(shared.STATE / ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "prepare":
            prepare()
        else:
            data, mount, directory = load_manifest()
            if args.action == "rollback":
                rollback(data, mount, directory)
            else:
                print(json.dumps({"status": data["status"], "tls_listening": shared.port_open(PORT),
                                  "reality_listening": shared.port_open(10443), "panel_listening": shared.port_open(2053),
                                  "backup_directory": str(directory)}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        sys.exit(1)
