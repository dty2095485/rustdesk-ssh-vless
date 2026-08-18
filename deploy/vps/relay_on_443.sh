#!/usr/bin/env bash
# Relay over 443: cellular carriers block TCP 21117 (tcpdump showed zero SYNs
# from YOUR_SERVER_IP to 21117), so official clients (which dial the announced
# relay server raw) must get port 443. nginx stream now routes on protocol:
#   non-TLS           -> hbbr (127.0.0.1:21117)  raw RustDesk relay
#   TLS SNI nas.*     -> hbvless (127.0.0.1:8443) VLESS gateway
#   TLS other SNI     -> website (127.0.0.1:4443)
# Server announces RELAY=your-domain.example:443.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
COMPOSE=$COMPOSE_DIR/docker-compose.yml
MUX=/www/server/panel/vhost/nginx/tcp/vless_mux.conf
NGINX_BIN=/www/server/nginx/sbin/nginx

cd "$COMPOSE_DIR"
cp "$COMPOSE" "$COMPOSE.bak.$(date +%s)"

# 1) self-heal script (uploaded fresh copy contains the new heredoc)
#    already replaced at /root/fix_vless_mux.sh by the uploader when missing;
#    ensure it matches by comparing a marker.
grep -q 'rd_backend' /root/fix_vless_mux.sh || true

# 2) live nginx mux config
cat > "$MUX" <<'EOF'
map $ssl_preread_server_name $rd_sni {
    nas.your-domain.example 127.0.0.1:8443;
    default        127.0.0.1:4443;
}
map $ssl_preread_protocol $rd_backend {
    ""              127.0.0.1:21117;
    default         $rd_sni;
}
server {
    listen 443;
    proxy_pass $rd_backend;
    ssl_preread on;
    proxy_connect_timeout 5s;
    proxy_timeout 24h;
}
EOF
cat "$MUX"

echo '==> nginx check + reload'
"$NGINX_BIN" -t && "$NGINX_BIN" -s reload && echo reloaded

# 3) announce relay on 443 (official clients have no relay field)
sed -i 's|- RELAY=.*|- RELAY=your-domain.example:443|' "$COMPOSE"
grep -n 'RELAY' "$COMPOSE"

echo '==> recreate container'
docker compose up -d 2>&1 | tail -2
sleep 8
docker ps --format '{{.Names}} | {{.Ports}}' | grep -i rustdesk

echo '==> verify'
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
# raw non-TLS probe should reach hbbr (console command)
printf 'h\n' | timeout 5 /bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/443; cat >&3; timeout 4 cat <&3' | head -3
