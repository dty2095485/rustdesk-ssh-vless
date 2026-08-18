#!/usr/bin/env bash
echo '== UDP 21116 with payload, 45s =='
timeout 45 tcpdump -ni any -X -c 20 'udp and port 21116' 2>&1 | head -100
echo '== done =='
