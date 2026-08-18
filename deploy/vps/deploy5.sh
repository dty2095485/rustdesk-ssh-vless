#!/usr/bin/env bash
# hbvless deploy, round 3: use BT-managed cert, nginx mux, docker container.
set -euo pipefail
DOMAIN=nas.your-domain.example
NGINX_BIN=/www/server/nginx/sbin/nginx
VHOST_DIR=/www/server/panel/vhost/nginx
BT_CERT=/www/server/panel/vhost/cert/nas.your-domain.example
TS=$(date +%s)

echo '==> [1] use BT-managed cert'
install -d -m 700 /etc/rustdesk-vless
cp "$BT_CERT/fullchain.pem" /etc/rustdesk-vless/nas.fullchain.pem
cp "$BT_CERT/privkey.pem" /etc/rustdesk-vless/nas.key
chmod 600 /etc/rustdesk-vless/nas.fullchain.pem /etc/rustdesk-vless/nas.key
openssl x509 -in /etc/rustdesk-vless/nas.fullchain.pem -noout -subject -dates

echo '==> [2] cert auto-sync cron (BT renews; we copy + restart)'
cat > /etc/cron.d/rustdesk-vless-cert <<'EOF'
*/10 * * * * root cmp -s /www/server/panel/vhost/cert/nas.your-domain.example/fullchain.pem /etc/rustdesk-vless/nas.fullchain.pem || { cp /www/server/panel/vhost/cert/nas.your-domain.example/fullchain.pem /etc/rustdesk-vless/nas.fullchain.pem; cp /www/server/panel/vhost/cert/nas.your-domain.example/privkey.pem /etc/rustdesk-vless/nas.key; chmod 600 /etc/rustdesk-vless/nas.fullchain.pem /etc/rustdesk-vless/nas.key; docker restart hbvless 2>/dev/null; }
EOF
chmod 644 /etc/cron.d/rustdesk-vless-cert

echo '==> [3] remove redundant acme.sh LE entry (avoid double ACME renewal)'
~/.acme.sh/acme.sh --remove -d "$DOMAIN" --ecc || true

echo '==> [4] website 443 -> loopback + SNI mux'
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

echo '==> [5] docker image + hbvless container'
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

echo '==> [6] verification'
echo '--- 443 listeners ---'
ss -ltnp | grep ':443 ' || true
echo '--- website through mux ---'
curl -skI --max-time 10 https://your-domain.example | head -3
echo '--- nas SNI through mux (expect nas.your-domain.example cert) ---'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername "$DOMAIN" 2>/dev/null | grep -E 'subject=|issuer=' | head -2
echo '--- hbvless process ---'
docker top hbvless | tail -1

echo '==> DONE'
echo "    UUID: $(grep '^VLESS_UUID=' /etc/rustdesk-vless/hbvless.env | cut -d= -f2)"
