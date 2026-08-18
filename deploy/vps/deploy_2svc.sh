#!/usr/bin/env bash
# Split the merged container back into two containers:
#   rustdesk_rrsC : hbbs + hbbr (normal RustDesk server, direct mode)
#   rustdesk_gw   : hbvless only, shares rustdesk_rrsC's network namespace,
#                   so its tunnel lands on 127.0.0.1 (loopback gate passes)
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
cd "$COMPOSE_DIR"

echo '== build srv + gw images =='
mkdir -p /tmp/split-img
cat > /tmp/split-img/Dockerfile.srv <<'EOF'
FROM rustdesk/rustdesk-server-s6:1.1.11-tcpreg
RUN rm -f /etc/s6-overlay/s6-rc.d/user/contents.d/hbvless
EOF
cat > /tmp/split-img/Dockerfile.gw <<'EOF'
FROM rustdesk/rustdesk-server-s6:1.1.11-tcpreg
RUN rm -f /etc/s6-overlay/s6-rc.d/user/contents.d/hbbs /etc/s6-overlay/s6-rc.d/user/contents.d/hbbr
EOF
docker build -q -t rustdesk/rustdesk-server-s6:1.1.11-tcpreg-srv -f /tmp/split-img/Dockerfile.srv /tmp/split-img
docker build -q -t rustdesk/rustdesk-server-s6:1.1.11-tcpreg-gw  -f /tmp/split-img/Dockerfile.gw  /tmp/split-img

echo '== write 2-service compose =='
cp docker-compose.yml docker-compose.yml.bak.2svc.$(date +%s)
cat > docker-compose.yml <<'EOF'
services:
  rustdesk_rrsC:
    image: rustdesk/rustdesk-server-s6:1.1.11-tcpreg-srv
    deploy:
      resources:
        limits:
          cpus: ${CPUS}
          memory: ${MEMORY_LIMIT}
    environment:
        - RELAY=your-domain.example:443
        - ENCRYPTED_ONLY=0
        - RUST_LOG=debug
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
    labels:
      createdBy: "bt_apps"
    networks:
      - baota_net
  rustdesk_gw:
    image: rustdesk/rustdesk-server-s6:1.1.11-tcpreg-gw
    network_mode: "service:rustdesk_rrsC"
    depends_on:
      - rustdesk_rrsC
    environment:
        - VLESS_LISTEN=0.0.0.0:8443
        - VLESS_UUID=50597446-7fef-46ae-ae4e-290f80f77d06
        - VLESS_CERT=/etc/rustdesk-vless/nas.fullchain.pem
        - VLESS_KEY=/etc/rustdesk-vless/nas.key
        - VLESS_HBBS=127.0.0.1:21116
        - VLESS_HBBR=127.0.0.1:21117
        - RUST_LOG=debug
    restart: always
    volumes:
        - /etc/rustdesk-vless:/etc/rustdesk-vless:ro

networks:
  baota_net:
    external: true
EOF

echo '== recreate =='
docker compose up -d 2>&1 | tail -4
sleep 12
docker ps --format '{{.Names}} | {{.Status}} | {{.Ports}}' | grep -i rustdesk

echo '== processes (srv) =='
docker exec rustdesk_rrsc-rustdesk_rrsC-1 ps | grep -E 'hbbs|hbbr|hbvless' | grep -v grep
echo '== processes (gw) =='
docker exec rustdesk_rrsc-rustdesk_gw-1 ps | grep -E 'hbbs|hbbr|hbvless' | grep -v grep

echo '== verify routes =='
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
