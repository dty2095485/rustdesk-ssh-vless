#!/usr/bin/env bash
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c '
/command/s6-svstat /run/service/hbvless
echo "--- run head ---"; head -1 /run/service/hbvless/run
echo "--- ps ---"; ps | grep -E "hbvless" | grep -v grep || echo "(no hbvless proc)"
echo "--- try manual ---"; cd /run/service/hbvless && timeout 4 ./run; echo "manual exit=$?"
'
echo '--- container log tail ---'
docker logs --tail 10 rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | tail -10
