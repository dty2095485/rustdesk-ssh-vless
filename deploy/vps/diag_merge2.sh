#!/usr/bin/env bash
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c '
echo "--- /run/service ---"; ls -la /run/service/ 2>/dev/null
echo "--- /run/service/hbvless ---"; ls -la /run/service/hbvless/ 2>/dev/null || echo "(missing)"
echo "--- /run/service/hbbs ---"; ls -la /run/service/hbbs/ 2>/dev/null
echo "--- compiled db? ---"; ls /run/s6-rc/servicedirs 2>/dev/null | head; ls -d /run/s6-rc/servicedirs/hbvless 2>/dev/null || echo "(no hbvless in compiled db)"
echo "--- our source files ---"; ls -la /etc/s6-overlay/s6-rc.d/hbvless/
echo "--- user contents ---"; ls /etc/s6-overlay/s6-rc.d/user/contents.d/
echo "--- hbbs dependencies content ---"; cat /etc/s6-overlay/s6-rc.d/hbbs/dependencies | od -c | head -3
'
