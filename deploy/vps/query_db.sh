#!/usr/bin/env bash
set -e
docker cp rustdesk_rrsc-rustdesk_rrsC-1:/data/db_v2.sqlite3 /tmp/db_v2.sqlite3
docker cp rustdesk_rrsc-rustdesk_rrsC-1:/data/db_v2.sqlite3-wal /tmp/db_v2.sqlite3-wal 2>/dev/null || true
docker cp rustdesk_rrsc-rustdesk_rrsC-1:/data/db_v2.sqlite3-shm /tmp/db_v2.sqlite3-shm 2>/dev/null || true
echo '--- tables ---'
sqlite3 /tmp/db_v2.sqlite3 '.tables'
echo '--- schema of peer-ish tables ---'
sqlite3 /tmp/db_v2.sqlite3 '.schema' | head -30
echo '--- peer rows ---'
sqlite3 -header /tmp/db_v2.sqlite3 'select * from peer limit 20;' 2>/dev/null || true
