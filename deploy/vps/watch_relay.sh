#!/usr/bin/env bash
echo '--- relay server logs (pairing?) ---'
docker logs --since 300s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -iE 'relay' | tail -15
