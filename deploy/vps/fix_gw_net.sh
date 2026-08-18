#!/usr/bin/env bash
# Give the VLESS gateway its own network + port publishing; the official
# container keeps only the official 21115-21119 ports.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
cd "$COMPOSE_DIR"
cp docker-compose.yml docker-compose.yml.bak.gwnet.$(date +%s)

cat > docker-compose.yml <<'EOF'
services:
  rustdesk_rrsC:
    image: rustdesk/rustdesk-server-s6:1.1.11
    environment:
        - RELAY=your-domain.example
        - ENCRYPTED_ONLY=0
        - RUST_LOG=debug
    ports:
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
      baota_net:
        ipv4_address: 172.18.0.50
  rustdesk_gw:
    image: rustdesk/rustdesk-server-s6:1.1.11-tcpreg-gw
    depends_on:
      - rustdesk_rrsC
    environment:
        - VLESS_LISTEN=0.0.0.0:8443
        - VLESS_UUID=50597446-7fef-46ae-ae4e-290f80f77d06
        - VLESS_CERT=/etc/rustdesk-vless/nas.fullchain.pem
        - VLESS_KEY=/etc/rustdesk-vless/nas.key
        - VLESS_HBBS=172.18.0.50:21116
        - VLESS_NAT=172.18.0.50:21115
        - VLESS_HBBR=172.18.0.50:21117
        - RUST_LOG=debug
    ports:
        - 127.0.0.1:8443:8443
    restart: always
    volumes:
        - /etc/rustdesk-vless:/etc/rustdesk-vless:ro
    labels:
      createdBy: "bt_apps"
    networks:
      baota_net:
        ipv4_address: 172.18.0.51

networks:
  baota_net:
    external: true
EOF

docker compose up -d 2>&1 | tail -4
sleep 12
docker ps --format '{{.Names}} | {{.Status}} | {{.Ports}}' | grep -i rustdesk

echo '== srv processes (official only) =='
docker exec rustdesk_rrsc-rustdesk_rrsC-1 ps | grep -E 'hbbs|hbbr|hbvless' | grep -v grep
echo '== gw processes =='
docker exec rustdesk_rrsc-rustdesk_gw-1 ps | grep -E 'hbbs|hbbr|hbvless' | grep -v grep

echo '== verify =='
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
echo '== synthetic vless: register 21116 =='
( printf '\x00\x50\x59\x74\x46\x7f\xef\x46\xae\xae\x4e\x29\x0f\x80\xf7\x7d\x06\x00\x01\x52\x7c\x01\xac\x12\x00\x32'; sleep 3 ) \
  | timeout 8 openssl s_client -quiet -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | xxd | head -2
echo '== synthetic vless: relay 443 -> hbbr =='
( printf '\x00\x50\x59\x74\x46\x7f\xef\x46\xae\xae\x4e\x29\x0f\x80\xf7\x7d\x06\x00\x01\x01\xbb\x01\xac\x12\x00\x32'; sleep 3 ) \
  | timeout 8 openssl s_client -quiet -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | xxd | head -2
