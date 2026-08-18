#!/usr/bin/env bash
echo '--- force up ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /command/s6-svc -u /run/service/hbvless
sleep 4
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /command/s6-svstat /run/service/hbvless
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ps | grep -E "hbvless|hbbs|hbbr" | grep -v grep'
echo '--- e2e ---'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
curl -skI --max-time 10 https://your-domain.example | head -1
