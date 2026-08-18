#!/usr/bin/env bash
# Finish the 8444 port fix first (the stack was left down).
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
COMPOSE=$COMPOSE_DIR/docker-compose.yml
sed -i 's|- 127.0.0.1:8443:8443|- 127.0.0.1:8444:8443|' "$COMPOSE"
sed -i 's|127.0.0.1:8443|127.0.0.1:8444|' /www/server/panel/vhost/nginx/tcp/vless_mux.conf
sed -i 's|127.0.0.1:8443|127.0.0.1:8444|' /root/fix_vless_mux.sh
/www/server/nginx/sbin/nginx -t && /www/server/nginx/sbin/nginx -s reload
cd "$COMPOSE_DIR"
docker compose up -d 2>&1 | tail -2
sleep 8
docker ps --format '{{.Names}} | {{.Status}}' | grep -i rustdesk
ss -ltnp | grep -E ':(8443|8444|21117)\s' | head -6
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ps | grep -E "hbvless|hbbs|hbbr" | grep -v grep'
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
