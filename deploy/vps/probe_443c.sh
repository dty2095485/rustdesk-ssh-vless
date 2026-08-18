#!/usr/bin/env bash
echo "== capture 443 + 21117 while sending 200 raw bytes to 443 =="
( timeout 6 tcpdump -ni lo -c 20 'tcp and (port 443 or port 21117)' > /tmp/lo3.txt 2>&1 & )
sleep 0.7
timeout 4 bash -c 'exec 3<>/dev/tcp/127.0.0.1/443; head -c 200 /dev/urandom >&3; timeout 2 cat <&3; echo rc=$?'
sleep 1
cat /tmp/lo3.txt
