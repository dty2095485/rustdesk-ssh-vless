#!/usr/bin/env bash
set -euo pipefail
echo '==> recreate hbvless without inherited healthcheck'
docker rm -f hbvless >/dev/null 2>&1 || true
docker run -d --name hbvless --restart=always --network host \
    --no-healthcheck \
    --entrypoint /opt/rustdesk-vless/hbvless \
    -v /opt/rustdesk-vless:/opt/rustdesk-vless \
    -v /etc/rustdesk-vless:/etc/rustdesk-vless \
    -v /usr/lib64/libgcc_s.so.1:/lib/x86_64-linux-gnu/libgcc_s.so.1:ro \
    -v /usr/lib64/libgcc_s.so.1:/usr/lib/x86_64-linux-gnu/libgcc_s.so.1:ro \
    -v /usr/lib64/libgcc_s.so.1:/lib64/libgcc_s.so.1:ro \
    --env-file /etc/rustdesk-vless/hbvless.env \
    rustdesk/rustdesk-server-s6:1.1.11
sleep 2
docker ps --format '{{.Names}} | {{.Status}}' | grep hbvless
ss -ltnp | grep ':8443' || true
echo '--- nas SNI end-to-end ---'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
echo '--- website ---'
curl -skI --max-time 10 https://your-domain.example | head -1
