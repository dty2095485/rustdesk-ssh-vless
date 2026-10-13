#!/usr/bin/env python3
"""Write the untracked Compose environment file on the deployment host."""

import argparse
import os


def read_one_line(path):
    with open(path, "r") as handle:
        value = handle.read().strip()
    if not value or "\n" in value or "\r" in value:
        raise RuntimeError("Invalid single-line value in " + path)
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--vless-uuid-file", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--container-name", default="rustdesk-server-canary")
    args = parser.parse_args()

    values = [
        ("IMAGE_TAG", args.image_tag),
        ("CONTAINER_NAME", args.container_name),
        ("DOCKERFILE", "docker-combined/Dockerfile.runtime"),
        (
            "RUSTDESK_BASE_IMAGE",
            "rustdesk/rustdesk-server-s6:1.1.17-vless-combined-r2-ssh",
        ),
        (
            "XUI_IMAGE",
            "ghcr.io/mhsanaei/3x-ui:v3.8.5@sha256:"
            "e0f90c10902e0e74f947d5a9efe017b273804477430233bbfc4918542ffe366c",
        ),
        ("S6_ARCH", "x86_64"),
        ("XUI_ENABLE_FAIL2BAN", "false"),
        ("XUI_DB_TYPE", ""),
        ("XUI_DB_DSN", ""),
        ("XUI_CERT_DIR", "/root/my-app/ssl"),
        ("RELAY", "example.com"),
        ("ENCRYPTED_ONLY", "0"),
        ("RUST_LOG", "debug"),
        ("VLESS_UUID", read_one_line(args.vless_uuid_file)),
        ("TLS_CERT_FILE", "/etc/rustdesk-vless/nas.fullchain.pem"),
        ("TLS_KEY_FILE", "/etc/rustdesk-vless/nas.key"),
        ("VLESS_TLS_HANDSHAKE_TIMEOUT_SECS", "10"),
        ("VLESS_HEADER_TIMEOUT_SECS", "10"),
        ("VLESS_UPSTREAM_CONNECT_TIMEOUT_SECS", "5"),
        ("VLESS_MAX_CONNECTIONS", "1024"),
        ("SSH_HOST_PORT", "2222"),
        ("SSH_AUTHORIZED_KEYS", ""),
    ]
    output = os.path.abspath(args.output)
    with open(output, "w") as handle:
        for key, value in values:
            if "\n" in value or "\r" in value:
                raise RuntimeError("Unexpected newline in " + key)
            handle.write("{}={}\n".format(key, value))
    os.chmod(output, 0o600)
    print("Compose environment prepared with {} keys".format(len(values)))


if __name__ == "__main__":
    main()
