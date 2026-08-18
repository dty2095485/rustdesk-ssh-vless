#!/usr/bin/env bash
set -euo pipefail
cd /www/dk_project/dk_app/rustdesk/rustdesk_rrsC
echo '== rebuild gw image: also drop hbvless dependencies on hbbs/hbbr =='
mkdir -p /tmp/split-img
cat > /tmp/split-img/Dockerfile.gw <<'EOF'
FROM rustdesk/rustdesk-server-s6:1.1.11-tcpreg
RUN rm -f /etc/s6-overlay/s6-rc.d/user/contents.d/hbbs /etc/s6-overlay/s6-rc.d/user/contents.d/hbbr \
 && rm -f /etc/s6-overlay/s6-rc.d/hbvless/dependencies
EOF
docker build -q -t rustdesk/rustdesk-server-s6:1.1.11-tcpreg-gw -f /tmp/split-img/Dockerfile.gw /tmp/split-img
docker compose up -d --force-recreate 2>&1 | tail -3
sleep 10
docker ps --format '{{.Names}} | {{.Status}}' | grep -i rustdesk
echo '== gw processes =='
docker exec rustdesk_rrsc-rustdesk_gw-1 ps | grep -E 'hbbs|hbbr|hbvless' | grep -v grep
echo '== srv processes =='
docker exec rustdesk_rrsc-rustdesk_rrsC-1 ps | grep -E 'hbbs|hbbr|hbvless' | grep -v grep
echo '== routes =='
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
