#!/usr/bin/env bash
# Bake only the new hbbs (TCP register loopback-gated) into the existing
# merged image tag and force-recreate the container.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
cd "$COMPOSE_DIR"
IMG="rustdesk/rustdesk-server-s6:$(grep -E '^VERSION=' .env | head -1 | cut -d= -f2 | tr -d '"' | tr -d "'")"
echo "== image tag: $IMG"

mkdir -p /tmp/hbbs-only
cp /tmp/hbbs-new /tmp/hbbs-only/hbbs
chmod +x /tmp/hbbs-only/hbbs
cp /usr/lib64/libgcc_s.so.1 /tmp/hbbs-only/libgcc_s.so.1
cat > /tmp/hbbs-only/Dockerfile <<EOF
FROM $IMG
COPY hbbs /usr/bin/hbbs
COPY libgcc_s.so.1 /lib64/libgcc_s.so.1
EOF
docker build -q -t "$IMG" /tmp/hbbs-only

docker compose up -d --force-recreate 2>&1 | tail -2
sleep 8
docker ps --format '{{.Names}} | {{.Status}}' | grep -i rustdesk
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ls -la /usr/bin/hbbs /usr/bin/hbbr /usr/bin/hbvless' 
