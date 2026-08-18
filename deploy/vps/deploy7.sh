#!/usr/bin/env bash
# hbvless container via existing s6 image + host libgcc mount (no docker pull).
set -euo pipefail

echo '==> [5a] ensure host libgcc'
if [ -f /usr/lib64/libgcc_s.so.1 ]; then
  echo '    /usr/lib64/libgcc_s.so.1 present'
else
  echo '    installing libgcc via yum'
  yum install -y -q libgcc
fi

echo '==> [5b] run container (existing image, host network)'
docker rm -f hbvless >/dev/null 2>&1 || true
docker run -d --name hbvless --restart=always --network host \
    --entrypoint /opt/rustdesk-vless/hbvless \
    -v /opt/rustdesk-vless:/opt/rustdesk-vless \
    -v /etc/rustdesk-vless:/etc/rustdesk-vless \
    -v /usr/lib64/libgcc_s.so.1:/lib/x86_64-linux-gnu/libgcc_s.so.1:ro \
    -v /usr/lib64/libgcc_s.so.1:/usr/lib/x86_64-linux-gnu/libgcc_s.so.1:ro \
    -v /usr/lib64/libgcc_s.so.1:/lib64/libgcc_s.so.1:ro \
    --env-file /etc/rustdesk-vless/hbvless.env \
    rustdesk/rustdesk-server-s6:1.1.11
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
