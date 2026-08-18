#!/usr/bin/env bash
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
cd "$COMPOSE_DIR"
docker compose up -d 2>&1 | tail -3
sleep 8
docker ps --format '{{.Names}} | {{.Status}}' | grep -i rustdesk
ss -ltnp | grep -E ':(8443|21117)\s' | head -4
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ps | grep -E "hbvless|hbbs|hbbr" | grep -v grep'
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
