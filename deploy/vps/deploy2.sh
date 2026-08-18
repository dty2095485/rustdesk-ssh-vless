#!/usr/bin/env bash
# Deploy hbvless behind BT-nginx SNI mux on 443 (website stays on your-domain.example).
set -euo pipefail
DOMAIN=nas.your-domain.example
NGINX_BIN=/www/server/nginx/sbin/nginx
VHOST_DIR=/www/server/panel/vhost/nginx
TS=$(date +%s)

echo '==> [0] preflight: who else listens on TCP 443 in http configs'
grep -rn 'listen.*443' "$VHOST_DIR"/*.conf /www/server/nginx/conf/*.conf 2>/dev/null | grep -v '127.0.0.1:443' || true

echo '==> [1] install hbvless binary + unit'
install -d -m 755 /opt/rustdesk-vless /etc/rustdesk-vless
install -m 755 /tmp/hbvless /opt/rustdesk-vless/hbvless
install -m 644 /tmp/rustdesk-hbvless.service /etc/systemd/system/rustdesk-hbvless.service
echo '    binary ldd check:'
ldd /opt/rustdesk-vless/hbvless | grep -i 'not found' && { echo 'ERROR: missing shared libs'; exit 1; } || echo '    libs OK'

echo '==> [2] UUID + env'
UUID=$(cat /proc/sys/kernel/random/uuid)
umask 077
cat > /etc/rustdesk-vless/hbvless.env <<EOF
VLESS_UUID=$UUID
VLESS_LISTEN=127.0.0.1:8443
VLESS_CERT=/etc/rustdesk-vless/nas.fullchain.pem
VLESS_KEY=/etc/rustdesk-vless/nas.key
VLESS_HBBS=127.0.0.1:21116
VLESS_HBBR=127.0.0.1:21117
EOF
echo "$UUID" > /etc/rustdesk-vless/uuid.txt
chmod 600 /etc/rustdesk-vless/hbvless.env /etc/rustdesk-vless/uuid.txt

echo '==> [3] cert: renew nas.your-domain.example (acme.sh, webroot)'
cat > "$VHOST_DIR/nas.your-domain.example.conf" <<'EOF'
server
{
    listen 80;
    server_name nas.your-domain.example;
    root /www/wwwroot/nas.your-domain.example;
    index index.html;
    location ~ /.well-known {
        allow all;
    }
}
EOF
mkdir -p /www/wwwroot/nas.your-domain.example/.well-known/acme-challenge
chown -R www:www /www/wwwroot/nas.your-domain.example/.well-known
"$NGINX_BIN" -t && "$NGINX_BIN" -s reload
sleep 1
if ! ~/.acme.sh/acme.sh --renew -d "$DOMAIN" --force --webroot /www/wwwroot/nas.your-domain.example; then
  echo '    renew failed, trying fresh issue via letsencrypt'
  ~/.acme.sh/acme.sh --issue -d "$DOMAIN" --webroot /www/wwwroot/nas.your-domain.example \
      --server letsencrypt --register-account -m admin@your-domain.example
fi
openssl x509 -in ~/.acme.sh/"$DOMAIN"/fullchain.cer -noout -subject -dates
~/.acme.sh/acme.sh --install-cert -d "$DOMAIN" \
    --fullchain-file /etc/rustdesk-vless/nas.fullchain.pem \
    --key-file /etc/rustdesk-vless/nas.key \
    --reloadcmd 'systemctl try-restart rustdesk-hbvless'
chmod 600 /etc/rustdesk-vless/nas.key

echo '==> [4] move website 443 to loopback + SNI mux in stream'
cp "$VHOST_DIR/your-domain.example.conf" "$VHOST_DIR/your-domain.example.conf.vlessbak.$TS"
sed -i 's/^\(\s*\)listen 443 ssl;$/\1listen 127.0.0.1:443 ssl;/' "$VHOST_DIR/your-domain.example.conf"
grep -n 'listen' "$VHOST_DIR/your-domain.example.conf" | head -5
cat > "$VHOST_DIR/tcp/vless_mux.conf" <<'EOF'
# VLESS SNI mux: nas.your-domain.example -> hbvless (127.0.0.1:8443), others -> website (127.0.0.1:443)
map $ssl_preread_server_name $vless_backend {
    nas.your-domain.example 127.0.0.1:8443;
    default        127.0.0.1:443;
}
server {
    listen 443;
    proxy_pass $vless_backend;
    ssl_preread on;
    proxy_connect_timeout 5s;
    proxy_timeout 600s;
}
EOF
"$NGINX_BIN" -t && "$NGINX_BIN" -s reload
sleep 1

echo '==> [5] start hbvless'
systemctl daemon-reload
systemctl enable --now rustdesk-hbvless
sleep 2
systemctl --no-pager --lines=8 status rustdesk-hbvless || true

echo '==> [6] verification'
echo '--- listeners on 443 ---'
ss -ltnp | grep ':443 ' || true
echo '--- local TLS handshake to hbvless ---'
echo Q | openssl s_client -connect 127.0.0.1:8443 -servername "$DOMAIN" 2>/dev/null | grep -E 'subject=|issuer=|Verification' | head -4
echo '--- website still OK (through mux) ---'
curl -skI --max-time 10 https://your-domain.example | head -3
echo '--- nas SNI check (should show nas cert via mux->8443) ---'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername "$DOMAIN" 2>/dev/null | grep -E 'subject=|issuer=' | head -2

echo '==> DONE'
echo "    UUID: $UUID"
