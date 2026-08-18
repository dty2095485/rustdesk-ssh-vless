#!/usr/bin/env bash
bash /tmp/relay_probe2.sh > /dev/null 2>&1
sleep 1
echo '--- hbbr relay/auth logs ---'
docker logs --since 15s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -iE 'relay|auth' | tail -6
echo '--- running hbbr binary info ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ls -la /usr/bin/hbbr; ps | grep hbbr | grep -v grep'
