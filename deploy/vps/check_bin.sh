#!/usr/bin/env bash
echo '--- local uploaded binary ---'
md5sum /tmp/hbbr-new /tmp/hbbs-new 2>/dev/null
echo '--- running container binaries ---'
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c 'md5sum /usr/bin/hbbr /usr/bin/hbbs; ls -la /usr/bin/hbbr'
echo '--- image layers ---'
docker inspect rustdesk/rustdesk-server-s6:1.1.11-tcpreg --format '{{.Id}} {{.Created}}'
docker inspect rustdesk_rrsc-rustdesk_rrsC-1 --format '{{.Image}} {{.State.StartedAt}}'
