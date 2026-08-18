#!/usr/bin/env bash
echo '--- compose metadata ---'
docker inspect rustdesk_rrsc-rustdesk_rrsC-1 --format '{{json .Config.Labels}}' | tr ',' '\n' | grep -i compose
echo '--- mounts ---'
docker inspect rustdesk_rrsc-rustdesk_rrsC-1 --format '{{json .Mounts}}'
echo '--- compose files on disk ---'
ls /root/docker-compose.yml /root/docker-compose.yaml 2>/dev/null
docker compose ls 2>/dev/null
find / -maxdepth 3 -name 'docker-compose*.y*ml' 2>/dev/null | head -5
