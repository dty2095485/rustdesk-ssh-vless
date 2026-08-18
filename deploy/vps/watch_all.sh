#!/usr/bin/env bash
echo '--- established connections on 21116 in container ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'netstat -tn 2>/dev/null | grep 21116 || echo "(none)"'
echo '--- all Tcp connection sources (recent) ---'
docker logs --since 120s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep 'Tcp connection' | grep -v '117.144' | tail -8
