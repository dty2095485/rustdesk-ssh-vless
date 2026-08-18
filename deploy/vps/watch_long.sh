#!/usr/bin/env bash
echo "capture start: $(date '+%F %T')"
timeout 600 tcpdump -n -i any 'tcp and (port 8443 or port 21117) and tcp[tcpflags] & tcp-syn != 0' 2>/dev/null | grep -vE '127.0.0.1|172\.' | head -40
echo "capture end: $(date '+%F %T')"
