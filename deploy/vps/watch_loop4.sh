#!/usr/bin/env bash
sleep 170
echo '--- all 127.0.0.1 connection events (3min window) ---'
docker logs --since 170s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep 'Tcp connection' | grep '127.0.0.1'
echo '--- done ---'
