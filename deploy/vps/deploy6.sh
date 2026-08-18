#!/usr/bin/env bash
# hbvless container: debian:bookworm-slim runtime (steps 5-6).
set -euo pipefail
NGINX_BIN=/www/server/nginx/sbin/nginx

echo '==> [5a] pull slim base'
docker pull -q debian:bookworm-slim

echo '==> [5b] dry-run binary in base image'
docker run --rm -v /opt/rustdesk-vless:/opt/rustdesk-vless debian:bookworm-slim /opt/rustdesk-vless/hbvless 2>&1 | head -3 || true

if ! docker run --rm -v /opt/rustdesk-vless:/opt/rustdesk-vless debian:bookworm-slim /opt/rustdesk-vless/hbvless >/tmp/hbout 2>&1; then
  if grep -q 'libgcc_s' /tmp/hbout; then
    echo '    libgcc missing, building derived image'
    mkdir -p /tmp/hbvless-build
    cat > /tmp/hbvless-build/Dockerfile <<'EOF'
FROM debian:bookworm-slim
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libgcc-s1 \
    && rm -rf /var/lib/apt/lists/*
EOF
    docker build -q -t hbvless:latest /tmp/hbvless-build
  else
    echo '    other error:'
    cat /tmp/hbout
    docker tag debian:bookworm-slim hbvless:latest
  fi
else
  docker tag debian:bookworm-slim hbvless:latest
fi
echo "    base image: hbvless:latest"

echo '==> [5c] run container (host network)'
docker rm -f hbvless >/dev/null 2>&1 || true
docker run -d --name hbvless --restart=always --network host \
    -v /opt/rustdesk-vless:/opt/rustdesk-vless \
    -v /etc/rustdesk-vless:/etc/rustdesk-vless \
    --env-file /etc/rustdesk-vless/hbvless.env \
    hbvless:latest /opt/rustdesk-vless/hbvless
sleep 2
docker logs --tail 10 hbvless

echo '==> [6] verification'
echo '--- 443 listeners ---'
ss -ltnp | grep ':443 ' || true
echo '--- website through mux ---'
curl -skI --max-time 10 https://your-domain.example | head -3
echo '--- nas SNI through mux (expect nas.your-domain.example cert) ---'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=|issuer=' | head -2
echo '--- hbvless process ---'
docker top hbvless | tail -1

echo '==> DONE'
echo "    UUID: $(grep '^VLESS_UUID=' /etc/rustdesk-vless/hbvless.env | cut -d= -f2)"
