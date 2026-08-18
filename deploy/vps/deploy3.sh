#!/usr/bin/env bash
# Full hbvless deployment (docker runtime, BT-nginx SNI mux, acme.sh cert).
set -euo pipefail
DOMAIN=nas.your-domain.example
NGINX_BIN=/www/server/nginx/sbin/nginx
VHOST_DIR=/www/server/panel/vhost/nginx
TS=$(date +%s)

# cleanup stray unit from the earlier aborted run
rm -f /etc/systemd/system/rustdesk-hbvless.service
systemctl daemon-reload || true

echo '==> [1] env + uuid'
install -d -m 755 /opt/rustdesk-vless /etc/rustdesk-vless
[ -x /opt/rustdesk-vless/hbvless ] || install -m 755 /tmp/hbvless /opt/rustdesk-vless/hbvless
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

echo '==> [2] cert for nas.your-domain.example'
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
  echo '    renew failed, fresh issue via letsencrypt'
  ~/.acme.sh/acme.sh --issue -d "$DOMAIN" --webroot /www/wwwroot/nas.your-domain.example \
      --server letsencrypt --register-account -m admin@your-domain.example
fi
openssl x509 -in ~/.acme.sh/"$DOMAIN"/fullchain.cer -noout -subject -dates
~/.acme.sh/acme.sh --install-cert -d "$DOMAIN" \
    --fullchain-file /etc/rustdesk-vless/nas.fullchain.pem \
    --key-file /etc/rustdesk-vless/nas.key \
    --reloadcmd 'docker restart hbvless'
chmod 600 /etc/rustdesk-vless/nas.key

echo '==> [3] website 443 -> loopback + SNI mux'
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

echo '==> [4] docker image + hbvless container'
mkdir -p /tmp/hbvless-build
cat > /tmp/hbvless-build/Dockerfile <<'EOF'
FROM rustdesk/rustdesk-server-s6:1.1.11
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libgcc-s1 \
    && rm -rf /var/lib/apt/lists/*
EOF
docker build -q -t hbvless:latest /tmp/hbvless-build
docker rm -f hbvless >/dev/null 2>&1 || true
docker run -d --name hbvless --restart=always --network host \
    -v /opt/rustdesk-vless:/opt/rustdesk-vless \
    -v /etc/rustdesk-vless:/etc/rustdesk-vless \
    --env-file /etc/rustdesk-vless/hbvless.env \
    hbvless:latest /opt/rustdesk-vless/hbvless
sleep 2
docker logs --tail 10 hbvless

echo '==> [5] verification'
echo '--- 443 listeners ---'
ss -ltnp | grep ':443 ' || true
echo '--- website through mux ---'
curl -skI --max-time 10 https://your-domain.example | head -3
echo '--- nas SNI through mux (expect nas.your-domain.example cert from hbvless) ---'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername "$DOMAIN" 2>/dev/null | grep -E 'subject=|issuer=' | head -2
echo '--- hbvless process ---'
docker top hbvless | tail -1

echo '==> DONE'
echo "    UUID: $UUID"
