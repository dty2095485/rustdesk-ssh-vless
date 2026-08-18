#!/usr/bin/env bash
docker run --rm --entrypoint /bin/sh rustdesk/rustdesk-server-s6:1.1.11 -c '
echo "--- hbbs service files ---"; ls -la /etc/s6-overlay/s6-rc.d/hbbs/
echo "--- type ---"; cat /etc/s6-overlay/s6-rc.d/hbbs/type 2>/dev/null
echo "--- run ---"; cat /etc/s6-overlay/s6-rc.d/hbbs/run 2>/dev/null
echo "--- up ---"; cat /etc/s6-overlay/s6-rc.d/hbbs/up 2>/dev/null
echo "--- user bundle contents ---"; ls /etc/s6-overlay/s6-rc.d/user/contents.d/ 2>/dev/null
'
