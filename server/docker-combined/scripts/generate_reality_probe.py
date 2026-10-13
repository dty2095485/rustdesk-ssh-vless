#!/usr/bin/env python3
"""Generate a local-only Xray probe config without printing credentials."""

import argparse
import json
import os


def load_env(path):
    values = {}
    with open(path, "r") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            values[key] = value
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--server", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, default=10443)
    parser.add_argument("--listen-port", type=int, default=31015)
    parser.add_argument("--access-log", default="/tmp/reality-probe-access.log")
    parser.add_argument("--error-log", default="/tmp/reality-probe-error.log")
    args = parser.parse_args()
    values = load_env(args.env)
    config = {
        "log": {
            "access": args.access_log,
            "error": args.error_log,
            "loglevel": "debug",
        },
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": args.listen_port,
                "protocol": "dokodemo-door",
                "settings": {
                    "address": "127.0.0.1",
                    "port": 22115,
                    "network": "tcp",
                },
            }
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": args.server,
                            "port": args.server_port,
                            "users": [
                                {
                                    "id": values["RD_VLESS_REALITY_UUID"],
                                    "encryption": "none",
                                    "flow": values["RD_VLESS_REALITY_FLOW"],
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "raw",
                    "security": "reality",
                    "realitySettings": {
                        "serverName": values["RD_VLESS_REALITY_SNI"],
                        "fingerprint": values["RD_VLESS_REALITY_FINGERPRINT"],
                        "password": values["RD_VLESS_REALITY_PUBLIC_KEY"],
                        "shortId": values["RD_VLESS_REALITY_SHORT_ID"],
                        "spiderX": "/",
                    },
                },
            }
        ],
    }
    output = os.path.abspath(args.output)
    with open(output, "w") as handle:
        json.dump(config, handle, separators=(",", ":"))
    os.chmod(output, 0o600)
    print("Reality probe config prepared")


if __name__ == "__main__":
    main()
