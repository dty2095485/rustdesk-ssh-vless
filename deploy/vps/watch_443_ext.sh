#!/usr/bin/env bash
echo "== watching external 443 + backend 21117 (25s) =="
timeout 25 tcpdump -ni any -c 30 'tcp and ( (src host EXAMPLE_CLIENT_IP and dst port 443) or dst port 21117 )' 2>&1
echo "== done =="
