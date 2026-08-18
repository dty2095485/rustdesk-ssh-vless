#!/usr/bin/env bash
# Rebuild merged image with corrected run script, recreate, verify.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC

echo '==> [1] rebuild image with fixed run script'
mkdir -p /tmp/merge-img
cp /opt/rustdesk-vless/hbvless /tmp/merge-img/hbvless
cat > /tmp/merge-img/Dockerfile <<'EOF'
FROM rustdesk/rustdesk-server-s6:1.1.11-tcpreg
COPY hbvless /usr/bin/hbvless
RUN chmod +x /usr/bin/hbvless \
 && mkdir -p /etc/s6-overlay/s6-rc.d/hbvless \
 && printf 'longrun' > /etc/s6-overlay/s6-rc.d/hbvless/type \
 && printf '#!/bin/sh\nsleep 3\n/usr/bin/hbvless\n' > /etc/s6-overlay/s6-rc.d/hbvless/run \
 && chmod +x /etc/s6-overlay/s6-rc.d/hbvless/run \
 && printf 'hbbs\nhbbr\n' > /etc/s6-overlay/s6-rc.d/hbvless/dependencies \
 && touch /etc/s6-overlay/s6-rc.d/user/contents.d/hbvless
EOF
docker build -q -t rustdesk/rustdesk-server-s6:1.1.11-tcpreg /tmp/merge-img

echo '==> [2] recreate'
cd "$COMPOSE_DIR"
docker compose up -d 2>&1 | tail -3
sleep 8
docker ps --format '{{.Names}} | {{.Status}}' | grep -i rustdesk

echo '==> [3] services + ports'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ps | grep -E "hbvless|hbbs|hbbr" | grep -v grep'
ss -ltnp | grep ':8443' | head -2

echo '==> [4] e2e'
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
