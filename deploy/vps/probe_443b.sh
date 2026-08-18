#!/usr/bin/env bash
echo "== nginx compiled map =="
/www/server/nginx/sbin/nginx -T 2>/dev/null | grep -B2 -A12 'rd_backend' | head -30
echo "== capture (443 + backends) during probe =="
( timeout 6 tcpdump -ni lo -c 20 'tcp and (port 443 or port 21117 or port 4443 or port 8443)' > /tmp/lo_cap2.txt 2>&1 & )
sleep 0.7
timeout 4 bash -c 'exec 3<>/dev/tcp/127.0.0.1/443; printf "h\n" >&3; timeout 2 cat <&3; echo "cat-rc=$?"'
sleep 1
cat /tmp/lo_cap2.txt
echo "== nginx error log tail =="
tail -5 /www/server/nginx/logs/error.log 2>/dev/null
