#!/usr/bin/env bash
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c '
ls -la /command/with-contenv /command/with-contev 2>&1
echo "---"; ls /command/ | wc -l; ls /command/ | grep -iE "contenv|contev"
echo "--- run hbvless with /bin/sh now ---"
cd /run/service/hbvless && sed -i "1s|.*|#!/bin/sh|" run && head -1 run
/command/s6-svc -t /run/service/hbvless 2>/dev/null; sleep 1
/command/s6-svc -u /run/service/hbvless; sleep 4
/command/s6-svstat /run/service/hbvless
ps | grep hbvless | grep -v grep || echo "(hbvless not running)"
'
