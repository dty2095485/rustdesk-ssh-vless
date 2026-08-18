#!/usr/bin/env bash
set -euo pipefail
echo '== s6 layout =='
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'ls /etc/s6-overlay/s6-rc.d/ ; echo ---contents.d--- ; ls /etc/s6-overlay/s6-rc.d/user/contents.d/ 2>/dev/null ; echo ---svc-dirs--- ; for d in hbbs hbbr hbvless; do echo $d:; ls /etc/s6-overlay/s6-rc.d/$d 2>/dev/null; done'
echo '== backup current merged container =='
docker commit rustdesk_rrsc-rustdesk_rrsC-1 rustdesk/rustdesk-server-s6:1.1.11-tcpreg-merged-bak
docker save rustdesk/rustdesk-server-s6:1.1.11-tcpreg-merged-bak -o /root/rustdesk-merged-container-backup.tar
tar czf /root/rustdesk-compose-backup.tar.gz -C /www/dk_project/dk_app/rustdesk/rustdesk_rrsC .
ls -la /root/rustdesk-merged-container-backup.tar /root/rustdesk-compose-backup.tar.gz
docker images | grep -E 'tcpreg' | head -10
