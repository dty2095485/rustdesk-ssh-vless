#!/bin/sh
set -eu
for firewall in iptables ip6tables; do
    "$firewall" -N RD_VPS3_PRIVATE 2>/dev/null || true
    "$firewall" -F RD_VPS3_PRIVATE
    "$firewall" -A RD_VPS3_PRIVATE -i lo -j RETURN
    "$firewall" -A RD_VPS3_PRIVATE -p tcp -m multiport --dports 21115:21119,2096,2222,8443,2053,22115:22117 -j DROP
    "$firewall" -A RD_VPS3_PRIVATE -p udp --dport 21116 -j DROP
    "$firewall" -A RD_VPS3_PRIVATE -j RETURN
    "$firewall" -C INPUT -j RD_VPS3_PRIVATE 2>/dev/null || "$firewall" -I INPUT 1 -j RD_VPS3_PRIVATE
done
