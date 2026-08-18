#!/usr/bin/env bash
echo '--- capturing UDP 21116 with hex payloads for 60s ---'
timeout 60 tcpdump -n -i any -X 'udp and port 21116' 2>&1 | grep -E '^[0-9]|0x[0-9a-f]+:' | head -80 || true
echo '--- done ---'
