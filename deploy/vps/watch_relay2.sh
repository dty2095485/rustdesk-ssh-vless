#!/usr/bin/env bash
echo '--- hbbr relay requests/pairings ---'
docker logs --since 600s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -iE 'relay' | tail -20
