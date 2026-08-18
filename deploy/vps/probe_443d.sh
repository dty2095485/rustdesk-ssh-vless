#!/usr/bin/env bash
( timeout 8 tcpdump -ni any -c 30 'host 127.0.0.1 and tcp and (port 443 or port 21117 or port 4443)' > /tmp/lo4.txt 2>&1 & )
sleep 1
echo "== control: curl 4443 =="
curl -sk --max-time 3 -o /dev/null -w 'http=%{http_code}\n' https://127.0.0.1:4443/
sleep 0.5
echo "== probe: 200 bytes to 443 =="
timeout 4 bash -c 'exec 3<>/dev/tcp/127.0.0.1/443; head -c 200 /dev/urandom >&3; timeout 2 cat <&3; echo rc=$?'
sleep 1
echo "== 443 conns =="
ss -tn 'sport = :443 or dport = :443' | head -5
cat /tmp/lo4.txt
