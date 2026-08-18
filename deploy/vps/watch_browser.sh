#!/usr/bin/env bash
echo "start: $(date '+%F %T')"
timeout 180 tcpdump -n -i any 'tcp and (port 8443 or port 21117) and tcp[tcpflags] & tcp-syn != 0' 2>/dev/null | grep -vE '127.0.0.1|172\.' | head -25
echo "end: $(date '+%F %T')"
