#!/usr/bin/env bash
echo "== direct to hbbr console =="
timeout 6 bash -c 'exec 3<>/dev/tcp/127.0.0.1/21117; printf "h\n" >&3; timeout 3 cat <&3; echo; echo "cat-rc=$?"'
echo "== via nginx 443 (non-TLS) =="
timeout 6 bash -c 'exec 3<>/dev/tcp/127.0.0.1/443; printf "h\n" >&3; timeout 3 cat <&3; echo; echo "cat-rc=$?"'
echo "== nginx version =="
/www/server/nginx/sbin/nginx -v 2>&1
echo "== lo capture during another 443 probe =="
( timeout 5 tcpdump -ni lo -c 8 'tcp and (port 21117 or port 4443 or port 8443)' > /tmp/lo_cap.txt 2>&1 & )
sleep 0.5
timeout 4 bash -c 'exec 3<>/dev/tcp/127.0.0.1/443; printf "h\n" >&3; timeout 2 cat <&3'
sleep 1
cat /tmp/lo_cap.txt
