#!/usr/bin/env bash
echo '--- container log locations ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 sh -c 'ls -la /var/log 2>/dev/null; ls /run/service 2>/dev/null; find / -name "*.log" -newer /etc/hostname 2>/dev/null | head -10; cat /run/service/hbbs/run 2>/dev/null | head -15'
echo '--- docker log driver + recent logs ---'
docker inspect rustdesk_rrsc-rustdesk_rrsC-1 --format '{{.HostConfig.LogConfig.Type}} {{.HostConfig.LogConfig.Config}}'
docker logs --tail 5 rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | head -8
