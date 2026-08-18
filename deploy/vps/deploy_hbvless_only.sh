#!/usr/bin/env bash
# Bake only the new hbvless (443 -> hbbr relay mapping) and recreate.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
cd "$COMPOSE_DIR"
IMG="rustdesk/rustdesk-server-s6:$(grep -E '^VERSION=' .env | head -1 | cut -d= -f2 | tr -d '"' | tr -d "'")"
echo "== image tag: $IMG"
mkdir -p /tmp/hbvless-only
cp /tmp/hbvless-new /tmp/hbvless-only/hbvless
chmod +x /tmp/hbvless-only/hbvless
cat > /tmp/hbvless-only/Dockerfile <<EOF
FROM $IMG
COPY hbvless /usr/bin/hbvless
EOF
docker build -q -t "$IMG" /tmp/hbvless-only
docker compose up -d --force-recreate 2>&1 | tail -2
sleep 8
docker ps --format '{{.Names}} | {{.Status}}' | grep -i rustdesk
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ls -la /usr/bin/hbvless'
