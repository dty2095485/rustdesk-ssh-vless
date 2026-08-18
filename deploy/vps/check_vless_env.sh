#!/usr/bin/env bash
echo '--- container env (VLESS) ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'env | grep -E "VLESS|RELAY" | sort'
echo '--- hbvless process cmdline ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ps | grep hbvless | grep -v grep; cat /proc/$(pgrep -f /usr/bin/hbvless | head -1)/environ 2>/dev/null | tr "\0" "\n" | grep VLESS'
