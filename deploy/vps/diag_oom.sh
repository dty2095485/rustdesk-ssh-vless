#!/usr/bin/env bash
echo '--- OOM evidence ---'
dmesg 2>/dev/null | grep -iE 'killed process|out of memory' | tail -8 || echo '(dmesg unavailable or empty)'
journalctl -k --no-pager 2>/dev/null | grep -iE 'killed process|oom' | tail -8 || true
echo '--- memory now ---'
free -m
echo '--- top memory consumers ---'
ps aux --sort=-%mem | head -8 | awk '{printf "%s %s %s%% %s\n", $1, $2, $4, $11}'
