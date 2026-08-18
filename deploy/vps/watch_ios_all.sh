#!/usr/bin/env bash
echo "== capture all traffic from iOS (120s) =="
timeout 120 tcpdump -ni any -c 300 'host YOUR_SERVER_IP' 2>&1 | grep -E 'IP 39|UDP|Flags'
echo "== done =="
