#!/usr/bin/env bash
# Rewrite compose cleanly (merged hbvless), recreate, finish merge.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
COMPOSE=$COMPOSE_DIR/docker-compose.yml
UUID=$(grep '^VLESS_UUID=' /etc/rustdesk-vless/hbvless.env | cut -d= -f2)

echo '==> [1] write compose'
cat > "$COMPOSE" <<'EOF'
services:
  rustdesk_rrsC:
    image: rustdesk/rustdesk-server-s6:${VERSION}
    #    container_name: ${CONTAINER_NAME}
    deploy:
      resources:
        limits:
          cpus: ${CPUS}
          memory: ${MEMORY_LIMIT}
    environment:
        - RELAY=${RUSTDESK_HOST_ADDR}:${RUSTDESK_PORT_HBBR}
        - ENCRYPTED_ONLY=1
        - VLESS_LISTEN=0.0.0.0:8443
        - VLESS_UUID=__UUID__
        - VLESS_CERT=/etc/rustdesk-vless/nas.fullchain.pem
        - VLESS_KEY=/etc/rustdesk-vless/nas.key
        - VLESS_HBBS=127.0.0.1:21116
        - VLESS_HBBR=127.0.0.1:21117
    ports:
        - 127.0.0.1:8443:8443
        - ${HOST_IP}:${RUSTDESK_PORT_NAT}:21115
        - ${HOST_IP}:${RUSTDESK_PORT_HBBS}:21116
        - ${HOST_IP}:${RUSTDESK_PORT_HBBS}:21116/udp
        - ${HOST_IP}:${RUSTDESK_PORT_HBBR}:21117
        - ${HOST_IP}:${RUSTDESK_PORT_WEB_CLIENT_1}:21118
        - ${HOST_IP}:${RUSTDESK_PORT_WEB_CLIENT_2}:21119
    restart: always
    volumes:
        - ${APP_PATH}/data:/data
        - /etc/rustdesk-vless:/etc/rustdesk-vless:ro
    labels:
      createdBy: "bt_apps"
    networks:
      - baota_net

networks:
  baota_net:
    external: true
EOF
sed -i "s/__UUID__/$UUID/" "$COMPOSE"

echo '==> [2] recreate container'
cd "$COMPOSE_DIR"
docker compose up -d 2>&1 | tail -3
sleep 6
docker ps --format '{{.Names}} | {{.Image}} | {{.Status}}' | grep -i rustdesk

echo '==> [3] in-container checks'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ps aux 2>/dev/null | grep -E "hbbs|hbbr|hbvless" | grep -v grep || ps | grep -E "hbbs|hbbr|hbvless"; netstat -ltnp 2>/dev/null | grep -E ":8443|:21116|:21117" || ss -ltnp | grep -E ":8443|:21116|:21117"'

echo '==> [4] host checks + remove old container'
ss -ltnp | grep ':8443' || echo '(no host 8443!)'
docker rm -f hbvless >/dev/null 2>&1 && echo 'old hbvless container removed' || true

echo '==> [5] update cert-sync cron'
sed -i 's|docker restart hbvless 2>/dev/null|docker exec rustdesk_rrsc-rustdesk_rrsC-1 /command/s6-svc -r /run/service/hbvless 2>/dev/null|' /etc/cron.d/rustdesk-vless-cert
cat /etc/cron.d/rustdesk-vless-cert

echo '==> [6] end-to-end'
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
