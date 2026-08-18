#!/usr/bin/env bash
echo '--- full fix log ---'
cat /var/log/vless-mux-fix.log
echo '--- journal for mux-fix service ---'
journalctl -u rustdesk-mux-fix.service --no-pager -n 40 | tail -30
echo '--- nginx now ---'
pgrep -a nginx || echo '(nginx down NOW)'
echo '--- 443 now ---'
ss -ltnp | grep ':443' || echo '(nothing on 443)'
echo '--- nginx error log tail ---'
tail -8 /www/wwwlogs/nginx_error.log
echo '--- bt panel watchdog tasks? ---'
crontab -l 2>/dev/null | head -10
ls /www/server/panel/class/ 2>/dev/null | head -3 >/dev/null && echo '(panel present)'
