#!/usr/bin/env bash
echo '--- entrypoint/cmd ---'
docker inspect rustdesk/rustdesk-server-s6:1.1.11 --format 'Entrypoint={{json .Config.Entrypoint}} Cmd={{json .Config.Cmd}}'
echo '--- service dirs in image ---'
docker run --rm --entrypoint /bin/sh rustdesk/rustdesk-server-s6:1.1.11 -c 'ls /run/service 2>/dev/null; echo ---; find / -maxdepth 4 -name "hbbs" -o -maxdepth 4 -name "hbbr" 2>/dev/null | grep -v proc | head; echo ---; ls /etc/s6* /package 2>/dev/null | head -20'
echo '--- hbbs run script ---'
docker run --rm --entrypoint /bin/sh rustdesk/rustdesk-server-s6:1.1.11 -c 'cat /run/service/hbbs/run 2>/dev/null | head -20'
