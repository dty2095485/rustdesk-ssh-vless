#!/usr/bin/env bash
echo '--- find db in container ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 sh -c 'find / -name "db_v2*" -o -name "*.sqlite3" 2>/dev/null | head -10'
echo '--- host sqlite3 ---'
command -v sqlite3 || echo '(no sqlite3 on host)'
