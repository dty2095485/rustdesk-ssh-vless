#!/usr/bin/env bash
# hbvless host port: 8444 -> 8443. 8444 was only a workaround for the old
# 0.0.0.0:8443 relay mapping, which is gone now; the user's security groups
# know 8443, not 8444.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
COMPOSE=$COMPOSE_DIR/docker-compose.yml
MUX=/www/server/panel/vhost/nginx/tcp/vless_mux.conf
NGINX_BIN=/www/server/nginx/sbin/nginx

cd "$COMPOSE_DIR"
cp "$COMPOSE" "$COMPOSE.bak.$(date +%s)"

# 1) self-heal script first: watchers may re-run it at any time
sed -i 's|nas.your-domain.example 127.0.0.1:8444;|nas.your-domain.example 127.0.0.1:8443;|' /root/fix_vless_mux.sh

# 2) container mapping: 127.0.0.1:8443 -> container 8443
sed -i 's|- 127.0.0.1:8444:8443|- 127.0.0.1:8443:8443|' "$COMPOSE"

# 3) recreate so the new mapping is live before nginx switches to it
docker compose up -d 2>&1 | tail -2
sleep 8

# 4) live nginx mux file -> 8443
sed -i 's|127.0.0.1:8444;|127.0.0.1:8443;|' "$MUX"
sed -i 's|127.0.0.1:8444)|127.0.0.1:8443)|' "$MUX"

echo '==> compose ports:'
grep -nE '8443|8444' "$COMPOSE"
echo '==> mux + self-heal script:'
grep -n '8443\|8444' "$MUX" /root/fix_vless_mux.sh
echo '==> container ports:'
docker ps --format '{{.Names}} | {{.Ports}}' | grep -i rustdesk
ss -ltnp | grep -E ':844[34]\s' | head -4

echo '==> reload nginx'
"$NGINX_BIN" -t && "$NGINX_BIN" -s reload && echo reloaded

echo '==> SNI verify'
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
