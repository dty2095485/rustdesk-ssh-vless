#!/usr/bin/env bash
# Merge hbvless into the rustdesk container as an s6 service.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
COMPOSE=$COMPOSE_DIR/docker-compose.yml
UUID=$(grep '^VLESS_UUID=' /etc/rustdesk-vless/hbvless.env | cut -d= -f2)

echo '==> [1] build merged image'
mkdir -p /tmp/merge-img
cp /opt/rustdesk-vless/hbvless /tmp/merge-img/hbvless
cat > /tmp/merge-img/Dockerfile <<'EOF'
FROM rustdesk/rustdesk-server-s6:1.1.11-tcpreg
COPY hbvless /usr/bin/hbvless
RUN chmod +x /usr/bin/hbvless \
 && mkdir -p /etc/s6-overlay/s6-rc.d/hbvless \
 && printf 'longrun' > /etc/s6-overlay/s6-rc.d/hbvless/type \
 && printf '#!/command/with-contev sh\nsleep 3\n/usr/bin/hbvless\n' > /etc/s6-overlay/s6-rc.d/hbvless/run \
 && chmod +x /etc/s6-overlay/s6-rc.d/hbvless/run \
 && printf 'hbbs\nhbbr\n' > /etc/s6-overlay/s6-rc.d/hbvless/dependencies \
 && touch /etc/s6-overlay/s6-rc.d/user/contents.d/hbvless
EOF
docker build -q -t rustdesk/rustdesk-server-s6:1.1.11-tcpreg /tmp/merge-img

echo '==> [2] compose: add port, volume, env'
cp "$COMPOSE" "$COMPOSE.mergebak.$(date +%s)"
sed -i "/RUSTDESK_PORT_NAT}:21115/i\        - 127.0.0.1:8443:8443" "$COMPOSE"
sed -i "s|      - \${APP_PATH}/data:/data|      - \${APP_PATH}/data:/data\n      - /etc/rustdesk-vless:/etc/rustdesk-vless:ro|" "$COMPOSE"
sed -i "/- ENCRYPTED_ONLY=1/a\        - VLESS_LISTEN=0.0.0.0:8443\n        - VLESS_UUID=$UUID\n        - VLESS_CERT=/etc/rustdesk-vless/nas.fullchain.pem\n        - VLESS_KEY=/etc/rustdesk-vless/nas.key\n        - VLESS_HBBS=127.0.0.1:21116\n        - VLESS_HBBR=127.0.0.1:21117" "$COMPOSE"
grep -n '8443\|rustdesk-vless\|VLESS_' "$COMPOSE"

echo '==> [3] recreate container'
cd "$COMPOSE_DIR"
docker compose up -d 2>&1 | tail -3
sleep 6
docker ps --format '{{.Names}} | {{.Image}} | {{.Status}}' | grep -i rustdesk

echo '==> [4] in-container checks'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ps aux | grep -E "hbbs|hbbr|hbvless" | grep -v grep; ss -ltnp 2>/dev/null | grep -E ":8443|:21116|:21117" || netstat -ltnp 2>/dev/null | grep -E ":8443|:21116|:21117"'

echo '==> [5] host checks + remove old container'
ss -ltnp | grep ':8443' || echo '(no host 8443!)'
docker rm -f hbvless >/dev/null 2>&1 && echo 'old hbvless container removed' || true

echo '==> [6] update cert-sync cron to restart only the hbvless service'
sed -i 's|docker restart hbvless 2>/dev/null|docker exec rustdesk_rrsc-rustdesk_rrsC-1 /command/s6-svc -r /run/service/hbvless 2>/dev/null|' /etc/cron.d/rustdesk-vless-cert
cat /etc/cron.d/rustdesk-vless-cert

echo '==> [7] end-to-end'
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
