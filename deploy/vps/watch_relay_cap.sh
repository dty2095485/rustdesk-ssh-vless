#!/usr/bin/env bash
echo '--- live capture: inbound TCP SYN to relay ports (90s) ---'
timeout 90 tcpdump -n -i any 'tcp and (port 21117 or port 8443 or port 8444) and tcp[tcpflags] & tcp-syn != 0' 2>/dev/null | grep -vE '127.0.0.1|172\.' | head -25
echo '--- capture done ---'
