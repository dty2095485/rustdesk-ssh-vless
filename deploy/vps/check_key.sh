#!/usr/bin/env bash
echo '--- /data/id_ed25519 exists? ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ls -la /data/id_ed25519 2>/dev/null || echo MISSING'
echo '--- derived public key (server key) ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'cat /data/id_ed25519 2>/dev/null | tr -d "\n" | base64 -d | tail -c 32 | base64'
echo '--- expected ---'
echo 'F5sWBBmQa1B27HuuEuRit52fWQ2cs5I3lZBYJLiD8KU='
echo '--- hbbr startup key log ---'
docker logs rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -E '^.*Key: ' | head -2
