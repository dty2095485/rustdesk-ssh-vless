#!/usr/bin/env python3
"""Prepare a copied 3x-ui database for the combined RustDesk container.

The existing proxy clients and Reality key pair are preserved. A dedicated
RustDesk client is added and routed only to the authenticated loopback ports;
all other destinations for that client are blackholed.
"""

import argparse
import json
import os
import re
import secrets
import sqlite3
import subprocess
import time
import uuid


RUSTDESK_EMAIL = "rustdesk-client"
RUSTDESK_PORTS = "22115-22117"


def public_key_from_private(container: str, private_key: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "/app/bin/xray-linux-amd64",
            "x25519",
            "-i",
            private_key,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    match = re.search(
        r"^(?:Password(?: \(PublicKey\))?|Public key):\s*(\S+)\s*$",
        result.stdout,
        re.M,
    )
    if not match:
        raise RuntimeError("Could not derive the Reality public key with Xray")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--client-env", required=True)
    parser.add_argument("--xray-container", default="sys_service_app")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT id, settings, stream_settings FROM inbounds "
            "WHERE port = 10443 AND protocol = 'vless' AND enable = 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("Enabled VLESS Reality inbound on port 10443 was not found")

        inbound_id, settings_text, stream_text = row
        settings = json.loads(settings_text)
        stream = json.loads(stream_text)
        clients = settings.setdefault("clients", [])

        rustdesk = next(
            (client for client in clients if client.get("email") == RUSTDESK_EMAIL),
            None,
        )
        now_ms = int(time.time() * 1000)
        if rustdesk is None:
            rustdesk = {
                "comment": "RustDesk authenticated transport only",
                "created_at": now_ms,
                "email": RUSTDESK_EMAIL,
                "enable": True,
                "expiryTime": 0,
                "flow": "xtls-rprx-vision",
                "id": str(uuid.uuid4()),
                "limitIp": 0,
                "reset": 0,
                "subId": secrets.token_hex(8),
                "tgId": 0,
                "totalGB": 0,
                "updated_at": now_ms,
            }
            clients.append(rustdesk)
        else:
            rustdesk["enable"] = True
            rustdesk["flow"] = "xtls-rprx-vision"
            rustdesk["updated_at"] = now_ms

        reality = stream.get("realitySettings", {})
        reality_client = reality.get("settings", {})
        server_names = (
            reality.get("serverNames")
            or ([reality_client.get("serverName")] if reality_client.get("serverName") else [])
        )
        short_ids = [value for value in (reality.get("shortIds") or []) if value]
        private_key = reality.get("privateKey", "")
        if not server_names or not short_ids or not private_key:
            raise RuntimeError("Reality SNI, short ID, or private key is missing")
        public_key = public_key_from_private(args.xray_container, private_key)

        template_row = connection.execute(
            "SELECT value FROM settings WHERE key = 'xrayTemplateConfig'"
        ).fetchone()
        if template_row is None:
            raise RuntimeError("xrayTemplateConfig setting was not found")
        template = json.loads(template_row[0])
        outbounds = template.setdefault("outbounds", [])
        outbounds[:] = [item for item in outbounds if item.get("tag") != "rustdesk-loopback"]
        outbounds.append({
            "tag": "rustdesk-loopback",
            "protocol": "freedom",
            "settings": {"finalRules": [
                {"action": "allow", "ip": ["127.0.0.1"], "port": RUSTDESK_PORTS},
                {"action": "block"},
            ]},
        })
        routing = template.setdefault("routing", {})
        rules = routing.setdefault("rules", [])
        rules = [
            rule
            for rule in rules
            if RUSTDESK_EMAIL not in (rule.get("user") or [])
        ]
        rustdesk_rules = [
            {
                "type": "field",
                "user": [RUSTDESK_EMAIL],
                "network": "tcp",
                "ip": ["127.0.0.1"],
                "port": RUSTDESK_PORTS,
                "outboundTag": "rustdesk-loopback",
            },
            {
                "type": "field",
                "user": [RUSTDESK_EMAIL],
                "outboundTag": "blocked",
            },
        ]
        insert_at = 1 if rules and rules[0].get("inboundTag") == ["api"] else 0
        rules[insert_at:insert_at] = rustdesk_rules
        routing["rules"] = rules

        connection.execute(
            "UPDATE inbounds SET listen = ?, settings = ? WHERE id = ?",
            ("127.0.0.1", json.dumps(settings, separators=(",", ":")), inbound_id),
        )
        connection.execute(
            "UPDATE settings SET value = ? WHERE key = 'xrayTemplateConfig'",
            (json.dumps(template, separators=(",", ":")),),
        )
        traffic = connection.execute(
            "SELECT id FROM client_traffics WHERE email = ?",
            (RUSTDESK_EMAIL,),
        ).fetchone()
        if traffic is None:
            connection.execute(
                "INSERT INTO client_traffics "
                "(inbound_id, enable, email, up, down, expiry_time, total, reset, "
                "last_online, last_sub_fetch, reset_day, reset_max, reset_count) "
                "VALUES (?, 1, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)",
                (inbound_id, RUSTDESK_EMAIL),
            )
        else:
            connection.execute(
                "UPDATE client_traffics SET inbound_id = ?, enable = 1 "
                "WHERE email = ?",
                (inbound_id, RUSTDESK_EMAIL),
            )

        # 3x-ui 3.8+ normalizes clients into dedicated tables. Older databases
        # only have the JSON and client_traffics records, so support both
        # schemas and remain idempotent across the panel's first-start upgrade.
        normalized = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'clients'"
        ).fetchone()
        if normalized is not None:
            client_row = connection.execute(
                "SELECT id FROM clients WHERE email = ?",
                (RUSTDESK_EMAIL,),
            ).fetchone()
            if client_row is None:
                cursor = connection.execute(
                    "INSERT INTO clients "
                    "(email, sub_id, uuid, flow, security, limit_ip, total_gb, "
                    "expiry_time, enable, tg_id, group_name, comment, reset, "
                    "created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 'auto', 0, 0, 0, 1, 0, '', ?, 0, ?, ?)",
                    (
                        RUSTDESK_EMAIL,
                        rustdesk["subId"],
                        rustdesk["id"],
                        rustdesk["flow"],
                        rustdesk["comment"],
                        rustdesk["created_at"],
                        rustdesk["updated_at"],
                    ),
                )
                client_id = cursor.lastrowid
            else:
                client_id = client_row[0]
                connection.execute(
                    "UPDATE clients SET sub_id = ?, uuid = ?, flow = ?, "
                    "security = 'auto', enable = 1, updated_at = ? WHERE id = ?",
                    (
                        rustdesk["subId"],
                        rustdesk["id"],
                        rustdesk["flow"],
                        rustdesk["updated_at"],
                        client_id,
                    ),
                )
            relation = connection.execute(
                "SELECT 1 FROM client_inbounds WHERE client_id = ? AND inbound_id = ?",
                (client_id, inbound_id),
            ).fetchone()
            if relation is None:
                connection.execute(
                    "INSERT INTO client_inbounds "
                    "(client_id, inbound_id, flow_override, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (client_id, inbound_id, rustdesk["flow"], now_ms),
                )
            else:
                connection.execute(
                    "UPDATE client_inbounds SET flow_override = ? "
                    "WHERE client_id = ? AND inbound_id = ?",
                    (rustdesk["flow"], client_id, inbound_id),
                )
        connection.commit()

        values = {
            "RD_VLESS_REALITY_SERVER": server_names[0],
            "RD_VLESS_REALITY_PORT": "443",
            "RD_VLESS_REALITY_UUID": rustdesk["id"],
            "RD_VLESS_REALITY_SNI": server_names[0],
            "RD_VLESS_REALITY_PUBLIC_KEY": public_key,
            "RD_VLESS_REALITY_SHORT_ID": short_ids[0],
            "RD_VLESS_REALITY_FINGERPRINT": "chrome",
            "RD_VLESS_REALITY_FLOW": "xtls-rprx-vision",
        }
        output_path = os.path.abspath(args.client_env)
        with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
            for key, value in values.items():
                if "\n" in value or "\r" in value:
                    raise RuntimeError(f"Unexpected newline in {key}")
                handle.write(f"{key}={value}\n")
        os.chmod(output_path, 0o600)
        print(
            "Prepared Reality database: "
            f"{len(clients) - 1} existing proxy client(s), 1 isolated RustDesk client"
        )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
