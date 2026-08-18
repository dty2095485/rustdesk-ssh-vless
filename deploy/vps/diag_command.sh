#!/usr/bin/env bash
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c '
echo "--- /command ---"; ls /command/ 2>/dev/null | head -15 || echo "(no /command)"
echo "--- real with-contev ---"; find / -name with-contev -maxdepth 6 2>/dev/null | head -3
echo "--- hbbs run head ---"; head -1 /run/service/hbbs/run
'
