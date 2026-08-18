#!/usr/bin/env bash
echo '--- image libc version ---'
docker run --rm --entrypoint /bin/sh rustdesk/rustdesk-server-s6:1.1.11 -c 'ls /lib/x86_64-linux-gnu/libc.so.6 /lib64/libc.so.6 2>/dev/null; /lib/x86_64-linux-gnu/libc.so.6 2>/dev/null | head -1'
echo '--- where hbbs lives in image ---'
docker run --rm --entrypoint /bin/sh rustdesk/rustdesk-server-s6:1.1.11 -c 'ls -la /usr/bin/hbbs /usr/bin/hbbr 2>/dev/null'
