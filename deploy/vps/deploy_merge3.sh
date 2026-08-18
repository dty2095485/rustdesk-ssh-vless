#!/usr/bin/env bash
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
echo '==> [1] remove old hbvless (holds 8443)'
docker rm -f hbvless >/dev/null 2>&1 && echo removed || true
echo '==> [2] start merged container'
cd "$COMPOSE_DIR"
docker compose up -d 2>&1 | tail -3
sleep 6
docker ps --format '{{.Names}} | {{.Image}} | {{.Status}}' | grep -i rustdesk
echo '==> [3] in-container checks'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ps 2>/dev/null | grep -E "hbbs|hbbr|hbvless" || ps aux | grep -E "hbbs|hbbr|hbvless" | grep -v grep'
echo '==> [4] host 8443 + cron + e2e'
ss -ltnp | grep ':8443' || echo '(no host 8443!)'
sed -i 's|docker restart hbvless 2>/dev/null|docker exec rustdesk_rrsc-rustdesk_rrsC-1 /command/s6-svc -r /run/service/hbvless 2>/dev/null|' /etc/cron.d/rustdesk-vless-cert
cat /etc/cron.d/rustdesk-vless-cert
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
