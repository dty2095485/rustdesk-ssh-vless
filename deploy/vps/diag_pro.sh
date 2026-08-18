#!/usr/bin/env bash
echo '--- processes inside rustdesk container ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 ps aux 2>/dev/null | head -15 || echo '(exec failed)'
echo '--- listening ports inside container ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 sh -c 'netstat -ltnp 2>/dev/null | head -20 || ss -ltnp | head -20' 2>/dev/null || echo '(netstat/ss unavailable)'
echo '--- api reachable inside container (21114) ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 sh -c 'wget -q -O- --timeout=5 http://127.0.0.1:21114/api/health 2>&1 | head -3; echo; wget -q -O- --timeout=5 http://127.0.0.1:21114/api/login 2>&1 | head -3' 2>/dev/null || echo '(wget unavailable or failed)'
echo '--- container log files ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 sh -c 'ls /var/log 2>/dev/null; ls / 2>/dev/null | head -20' 2>/dev/null
echo '--- hbbs config inside container ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 sh -c 'ls -la / 2>/dev/null | grep -iE "hbbs|rustdesk|license|key|\.env" ; cat /hbbs.ini 2>/dev/null | head -20; cat /.env 2>/dev/null | head -20; find / -maxdepth 2 -name "*.key" -o -maxdepth 2 -name "*license*" 2>/dev/null | head -5' 2>/dev/null
