#!/usr/bin/env bash
# Bake hbvless with 21115 (NAT-test TCP) support into the gw image and
# recreate the gw container.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
cd "$COMPOSE_DIR"
mkdir -p /tmp/gw-img
cp /tmp/hbvless-new /tmp/gw-img/hbvless
chmod +x /tmp/gw-img/hbvless
cat > /tmp/gw-img/Dockerfile <<'EOF'
FROM rustdesk/rustdesk-server-s6:1.1.11-tcpreg
RUN rm -f /etc/s6-overlay/s6-rc.d/user/contents.d/hbbs /etc/s6-overlay/s6-rc.d/user/contents.d/hbbr \
 && rm -f /etc/s6-overlay/s6-rc.d/hbvless/dependencies
COPY hbvless /usr/bin/hbvless
EOF
docker build -q -t rustdesk/rustdesk-server-s6:1.1.11-tcpreg-gw /tmp/gw-img
grep -q 'VLESS_NAT' docker-compose.yml || sed -i 's|- VLESS_HBBS=.*|- VLESS_HBBS=172.18.0.50:21116\n        - VLESS_NAT=172.18.0.50:21115|' docker-compose.yml
grep -n 'VLESS_' docker-compose.yml
docker compose up -d --force-recreate 2>&1 | tail -3
sleep 10
docker ps --format '{{.Names}} | {{.Status}}' | grep -i rustdesk
docker exec rustdesk_rrsc-rustdesk_gw-1 ps | grep hbvless | grep -v grep
