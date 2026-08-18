#!/usr/bin/env bash
# Capture iOS cellular SYNs toward relay port 21117 (75s window).
echo "== watching for SYNs from YOUR_SERVER_IP to 21117 =="
timeout 75 tcpdump -ni any -c 10 'src host YOUR_SERVER_IP and tcp dst port 21117' 2>&1
echo "== watch done =="
