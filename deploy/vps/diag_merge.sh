#!/usr/bin/env bash
echo '--- hbvless service state ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /command/s6-svstat /run/service/hbvless 2>&1 || true
echo '--- recent container logs ---'
docker logs --tail 20 rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | tail -20
echo '--- run script ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'cat /etc/s6-overlay/s6-rc.d/hbvless/run'
echo '--- manual hbvless run (5s) ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'timeout 5 /usr/bin/hbvless 2>&1 | head -5; echo exit=$?'
