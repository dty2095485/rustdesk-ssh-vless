#!/usr/bin/env bash
echo '--- pid directive ---'
grep -n '^pid' /www/server/nginx/conf/nginx.conf || echo '(no pid directive)'
echo '--- pid file ---'
ls -la /www/server/nginx/logs/nginx.pid 2>/dev/null
echo "content: [$(cat /www/server/nginx/logs/nginx.pid 2>/dev/null)]"
echo '--- running nginx ---'
pgrep -a nginx
echo '--- current site conf ---'
grep -n -E 'listen|server_port' /www/server/panel/vhost/nginx/your-domain.example.conf | head -5
echo '--- watcher log tail ---'
tail -6 /var/log/vless-mux-fix.log
echo '--- health ---'
curl -skI --max-time 10 https://your-domain.example | head -1
