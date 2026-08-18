#!/usr/bin/env bash
# Bake hbbs + hbbr + hbvless (all rebuilt); relay on 21117, VLESS via 443.
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
COMPOSE=$COMPOSE_DIR/docker-compose.yml

echo '==> [1] rebuild merged image with all three binaries'
mkdir -p /tmp/hbbs-img
cp /tmp/hbbs-new /tmp/hbbs-img/hbbs
cp /tmp/hbbr-new /tmp/hbbs-img/hbbr
chmod +x /tmp/hbbs-img/hbbs /tmp/hbbs-img/hbbr
cp /usr/lib64/libgcc_s.so.1 /tmp/hbbs-img/libgcc_s.so.1
cat > /tmp/hbbs-img/Dockerfile <<'EOF'
FROM rustdesk/rustdesk-server-s6:1.1.11
COPY hbbs /usr/bin/hbbs
COPY hbbr /usr/bin/hbbr
COPY libgcc_s.so.1 /lib64/libgcc_s.so.1
EOF
docker build -q -t rustdesk/rustdesk-server-s6:1.1.11-tcpreg /tmp/hbbs-img

mkdir -p /tmp/merge-img
cp /tmp/hbvless-new /tmp/merge-img/hbvless
cat > /tmp/merge-img/Dockerfile <<'EOF'
FROM rustdesk/rustdesk-server-s6:1.1.11-tcpreg
COPY hbvless /usr/bin/hbvless
RUN chmod +x /usr/bin/hbvless \
 && mkdir -p /etc/s6-overlay/s6-rc.d/hbvless \
 && printf 'longrun' > /etc/s6-overlay/s6-rc.d/hbvless/type \
 && printf '#!/command/with-contenv sh\nsleep 3\n/usr/bin/hbvless\n' > /etc/s6-overlay/s6-rc.d/hbvless/run \
 && chmod +x /etc/s6-overlay/s6-rc.d/hbvless/run \
 && printf 'hbbs\nhbbr\n' > /etc/s6-overlay/s6-rc.d/hbvless/dependencies \
 && touch /etc/s6-overlay/s6-rc.d/user/contents.d/hbvless
EOF
docker build -q -t rustdesk/rustdesk-server-s6:1.1.11-tcpreg /tmp/merge-img

echo '==> [2] compose: relay on 443, keyless hbbr, no external 8443'
grep -q 'RELAY=your-domain.example:443' "$COMPOSE" || sed -i 's|- RELAY=.*|- RELAY=your-domain.example:443|' "$COMPOSE"
grep -q 'ENCRYPTED_ONLY=0' "$COMPOSE" || sed -i 's|- ENCRYPTED_ONLY=.*|- ENCRYPTED_ONLY=0|' "$COMPOSE"
sed -i '\|${HOST_IP}:8443:21117|d' "$COMPOSE"
grep -n 'RELAY\|ENCRYPTED_ONLY\|8443\|21117' "$COMPOSE"

echo '==> [3] recreate'
cd "$COMPOSE_DIR"
docker compose up -d 2>&1 | tail -2
sleep 8
docker ps --format '{{.Names}} | {{.Status}}' | grep -i rustdesk

echo '==> [4] verify'
ss -ltnp | grep -E ':(8443|21117)\s' | head -4
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ps | grep -E "hbvless|hbbs|hbbr" | grep -v grep'
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
