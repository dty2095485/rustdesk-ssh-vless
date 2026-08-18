#!/usr/bin/env bash
echo '--- hbbs startup relay config ---'
docker logs rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -iE 'relay-servers' | tail -3
echo '--- relay requests / pairing recent ---'
docker logs --since 400s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -iE 'relay request|paired|auth' | tail -10
