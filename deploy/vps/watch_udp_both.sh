#!/usr/bin/env bash
echo '== full UDP 21115/21116 both directions, 60s =='
timeout 60 tcpdump -ni any -c 40 'udp and (port 21116 or port 21115)' 2>&1 | head -40
echo '== done =='
