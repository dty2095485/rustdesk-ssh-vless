#!/usr/bin/env bash
echo '== UDP 21115/21116 capture 90s =='
timeout 90 tcpdump -ni any -c 60 'udp and (port 21116 or port 21115)' 2>&1 | grep -E 'IP .*\.(21115|21116):' | head -50
echo '== done =='
