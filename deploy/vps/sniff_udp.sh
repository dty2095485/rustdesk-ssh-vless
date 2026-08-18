#!/usr/bin/env bash
set -e
if ! command -v tcpdump >/dev/null 2>&1; then
  yum install -y -q tcpdump >/dev/null 2>&1 || apt-get install -y -q tcpdump >/dev/null 2>&1
fi
echo '--- udp listeners on 21116 (host) ---'
ss -lunp | grep 21116 || echo '(none)'
echo '--- capturing UDP 21116 for 20s ---'
timeout 20 tcpdump -n -i any 'udp and port 21116' -c 30 2>&1 | head -30 || true
echo '--- done ---'
