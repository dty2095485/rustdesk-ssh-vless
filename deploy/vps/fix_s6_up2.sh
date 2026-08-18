#!/usr/bin/env bash
echo '--- remove down file + cycle ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c '
rm -f /run/service/hbvless/down
/command/s6-svc -d /run/service/hbvless
sleep 1
/command/s6-svc -u /run/service/hbvless
sleep 4
/command/s6-svstat /run/service/hbvless
ps | grep hbvless | grep -v grep || echo "(hbvless process NOT running)"
'
echo '--- container log tail ---'
docker logs --tail 8 rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | tail -8
