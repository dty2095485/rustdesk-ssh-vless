#!/usr/bin/env bash
# Official hbbs/hbbr (stock 1.1.11 image), key preserved via /data/id_ed25519.
# VLESS gateway stays separate; relay rides 443 through nginx into the
# container's non-loopback IP so the official hbbr treats it as a normal
# relay connection (not a console command).
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
cd "$COMPOSE_DIR"
cp docker-compose.yml docker-compose.yml.bak.official.$(date +%s)

cat > docker-compose.yml <<'EOF'
services:
  rustdesk_rrsC:
    image: rustdesk/rustdesk-server-s6:1.1.11
    environment:
        - RELAY=your-domain.example
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
      baota_net:
        ipv4_address: 172.18.0.50
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
        - VLESS_HBBS=172.18.0.50:21116
        - VLESS_HBBR=172.18.0.50:21117
        - RUST_LOG=debug
    restart: always
    volumes:
        - /etc/rustdesk-vless:/etc/rustdesk-vless:ro

networks:
  baota_net:
    external: true
EOF

# nginx raw 443 backend -> container IP (non-loopback)
sed -i 's|127.0.0.1:21117;|172.18.0.50:21117;|' /www/server/panel/vhost/nginx/tcp/vless_mux.conf
sed -i 's|127.0.0.1:21117;|172.18.0.50:21117;|' /root/fix_vless_mux.sh
grep -n '21117' /www/server/panel/vhost/nginx/tcp/vless_mux.conf
/www/server/nginx/sbin/nginx -t && /www/server/nginx/sbin/nginx -s reload && echo nginx-reloaded

docker compose up -d 2>&1 | tail -4
sleep 12
docker ps --format '{{.Names}} | {{.Status}} | {{.Ports}}' | grep -i rustdesk
echo '== srv processes (official) =='
docker exec rustdesk_rrsc-rustdesk_rrsC-1 ps | grep -E 'hbbs|hbbr' | grep -v grep
echo '== gw processes =='
docker exec rustdesk_rrsc-rustdesk_gw-1 ps | grep -E 'hbvless' | grep -v grep

echo '== verify routes =='
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
timeout 4 bash -c 'exec 3<>/dev/tcp/127.0.0.1/443; printf "\020\000\000\000probe" >&3; timeout 2 cat <&3 >/dev/null; echo probe-rc=$?'
docker logs --tail 20 rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -aE 'Key:|Private key' | head -4
