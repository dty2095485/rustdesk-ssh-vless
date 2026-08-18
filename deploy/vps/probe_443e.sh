#!/usr/bin/env bash
( timeout 7 tcpdump -ni any -c 40 'host 127.0.0.1 and tcp and (port 443 or port 21117)' > /tmp/lo5.txt 2>&1 & )
sleep 1
timeout 5 bash -c 'exec 3<>/dev/tcp/127.0.0.1/443; printf "\020\000\000\000xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" >&3; sleep 1; timeout 3 cat <&3; echo rc=$?' &
PROBE_PID=$!
sleep 1.2
echo "== conns during probe =="
ss -tnp 'sport = :443 or dport = :443 or dport = :21117 or sport = :21117' | head -8
wait $PROBE_PID 2>/dev/null
sleep 1
echo "== capture =="
cat /tmp/lo5.txt
