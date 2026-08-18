#!/usr/bin/env bash
echo '--- hbbs/hbbr logs around the drop ---'
docker logs --since 600s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -E '18:51:5|18:52:' | grep -vE 'api/heartbeat|relay request' | tail -20
