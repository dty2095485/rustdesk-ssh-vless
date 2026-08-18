#!/usr/bin/env bash
docker ps --format '{{.Names}} | {{.Status}}' | grep -i rustdesk
echo '--- recent container logs ---'
docker logs --tail 6 rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | tail -6
echo '--- listeners ---'
ss -ltnp | grep -E ':(8443|8444|21117)\s' | head -4
curl -skI --max-time 10 https://your-domain.example | head -1
