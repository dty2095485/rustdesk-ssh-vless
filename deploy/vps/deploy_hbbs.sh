#!/usr/bin/env bash
# Replace the rustdesk container's hbbs with the TCP-register build.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC

echo '==> [1] build derived image'
mkdir -p /tmp/hbbs-img
cp /tmp/hbbs-new /tmp/hbbs-img/hbbs
chmod +x /tmp/hbbs-img/hbbs
cat > /tmp/hbbs-img/Dockerfile <<'EOF'
FROM rustdesk/rustdesk-server-s6:1.1.11
COPY hbbs /usr/bin/hbbs
EOF
docker build -q -t rustdesk/rustdesk-server-s6:1.1.11-tcpreg /tmp/hbbs-img

echo '==> [2] update compose VERSION'
ls -la "$COMPOSE_DIR" | head -8
grep -n '^VERSION=' "$COMPOSE_DIR/.env" 2>/dev/null || echo '(no .env VERSION line!)'
sed -i 's|^VERSION=.*|VERSION=1.1.11-tcpreg|' "$COMPOSE_DIR/.env"
grep '^VERSION=' "$COMPOSE_DIR/.env"

echo '==> [3] recreate container'
cd "$COMPOSE_DIR"
docker compose up -d 2>&1 | tail -4
sleep 4
docker ps --format '{{.Names}} | {{.Image}} | {{.Status}}' | grep -i rustdesk

echo '==> [4] sanity: hbbs runs, ports up'
ss -ltnp | grep -E ':(21115|21116|21117)\s' | head -4
docker logs --tail 5 rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | head -6
