#!/usr/bin/env bash
# Temporarily enable debug logging for hbbs to trace connection closes.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
COMPOSE=$COMPOSE_DIR/docker-compose.yml
grep -q 'RUST_LOG' "$COMPOSE" || sed -i '/- ENCRYPTED_ONLY=1/a\        - RUST_LOG=debug' "$COMPOSE"
grep -n 'RUST_LOG' "$COMPOSE"
cd "$COMPOSE_DIR"
docker compose up -d 2>&1 | tail -2
sleep 6
docker ps --format '{{.Names}} | {{.Status}}' | grep -i rustdesk
echo '--- wait 45s and dump hbbs connection logs ---'
sleep 45
docker logs --tail 400 rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -iE 'tcp connection|register|closed' | tail -25
