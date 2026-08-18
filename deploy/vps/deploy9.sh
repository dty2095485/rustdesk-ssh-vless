#!/usr/bin/env bash
# Mux v2: stream 0.0.0.0:443 -> {nas.your-domain.example: 127.0.0.1:8443, default: 127.0.0.1:4443}
set -euo pipefail
NGINX_BIN=/www/server/nginx/sbin/nginx
VHOST_DIR=/www/server/panel/vhost/nginx
TS=$(date +%s)

echo '==> [1] edit site: 443 -> 127.0.0.1:4443, fix redirect condition'
cp "$VHOST_DIR/your-domain.example.conf" "$VHOST_DIR/your-domain.example.conf.vlessbak2.$TS"
sed -i 's/^\(\s*\)listen 443 ssl;$/\1listen 127.0.0.1:4443 ssl;/' "$VHOST_DIR/your-domain.example.conf"
sed -i 's/if (\$server_port != 443) {/if (\$server_port = 80) {/' "$VHOST_DIR/your-domain.example.conf"
grep -n -E 'listen|server_port' "$VHOST_DIR/your-domain.example.conf" | head -8

echo '==> [2] mux config'
cat > "$VHOST_DIR/tcp/vless_mux.conf" <<'EOF'
# VLESS SNI mux: nas.your-domain.example -> hbvless (127.0.0.1:8443), others -> website (127.0.0.1:4443)
map $ssl_preread_server_name $vless_backend {
    nas.your-domain.example 127.0.0.1:8443;
    default        127.0.0.1:4443;
}
server {
    listen 443;
    proxy_pass $vless_backend;
    ssl_preread on;
    proxy_connect_timeout 5s;
    proxy_timeout 600s;
}
EOF
"$NGINX_BIN" -t

echo '==> [3] full restart (port moved http->stream, reload cannot do it)'
"$NGINX_BIN" -s quit
for i in $(seq 1 20); do pgrep -x nginx >/dev/null || break; sleep 0.5; done
"$NGINX_BIN"
sleep 2

echo '==> [4] verification'
ss -ltnp | grep -E ':(443|4443|8443)\s' || true
echo '--- website through mux ---'
curl -skI --max-time 10 https://your-domain.example | head -3
echo '--- detian SNI cert ---'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
echo '--- nas SNI cert (expect nas.your-domain.example) ---'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
