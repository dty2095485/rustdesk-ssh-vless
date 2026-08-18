#!/usr/bin/env bash
echo '--- hbbs relay-servers state (console) ---'
printf 'rs\n' | timeout 3 nc 127.0.0.1 21115 2>/dev/null || printf 'rs\n' | timeout 3 nc 127.0.0.1 21116 2>/dev/null || echo '(console unreachable)'
echo '--- live capture: any TCP from cellular to relay ports ---'
timeout 90 tcpdump -n -i any 'tcp and (port 21117 or port 8443) and tcp[tcpflags] & tcp-syn != 0' 2>/dev/null | grep -v '127.0.0.1' | head -20
echo '--- capture done ---'
