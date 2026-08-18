#!/usr/bin/env bash
docker cp rustdesk_rrsc-rustdesk_rrsC-1:/data/db_v2.sqlite3 /tmp/db_v2.sqlite3 2>/dev/null
docker cp rustdesk_rrsc-rustdesk_rrsC-1:/data/db_v2.sqlite3-wal /tmp/db_v2.sqlite3-wal 2>/dev/null
echo '--- peers with recent activity ---'
sqlite3 -header /tmp/db_v2.sqlite3 "select id, hex(uuid), length(pk) as pk_len, created_at, info from peer where id in ('150387293','277358702');"
