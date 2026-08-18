#!/usr/bin/env bash
docker run --rm --entrypoint /bin/sh rustdesk/rustdesk-server-s6:1.1.11 -c 'ls -la /lib64 2>/dev/null; echo ---; ls -la /lib 2>/dev/null; echo ---; ls /lib/x86_64-linux-gnu 2>/dev/null | head -20'
