#!/usr/bin/env bash
nohup timeout 180 tcpdump -n -i any 'udp and port 21116' -w /tmp/udp_cap.pcap >/dev/null 2>&1 &
echo "tcpdump started pid $!"
