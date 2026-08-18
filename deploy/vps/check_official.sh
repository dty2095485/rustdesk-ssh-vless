#!/usr/bin/env bash
echo '--- UDP register traffic (official client path) still flowing ---'
timeout 25 tcpdump -n -i any 'udp and port 21116' 2>/dev/null | head -10 || true
echo '--- done ---'
