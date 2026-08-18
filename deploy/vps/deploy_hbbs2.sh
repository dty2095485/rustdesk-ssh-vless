#!/usr/bin/env bash
# Rebuild the derived image with libgcc_s baked in, recreate container.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC

echo '==> [1] rebuild derived image with libgcc_s'
mkdir -p /tmp/hbbs-img
cp /tmp/hbbs-new /tmp/hbbs-img/hbbs
chmod +x /tmp/hbbs-img/hbbs
cp /usr/lib64/libgcc_s.so.1 /tmp/hbbs-img/libgcc_s.so.1
cat > /tmp/hbbs-img/Dockerfile <<'EOF'
FROM rustdesk/rustdesk-server-s6:1.1.11
COPY hbbs /usr/bin/hbbs
COPY libgcc_s.so.1 /lib64/libgcc_s.so.1
EOF
docker build -q -t rustdesk/rustdesk-server-s6:1.1.11-tcpreg /tmp/hbbs-img

echo '==> [2] recreate container'
cd "$COMPOSE_DIR"
docker compose up -d 2>&1 | tail -3
sleep 4
docker ps --format '{{.Names}} | {{.Image}} | {{.Status}}' | grep -i rustdesk

echo '==> [3] sanity: hbbs log + ports'
docker logs --tail 6 rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | head -8
ss -ltnp | grep -E ':(21116)\s' | head -2
