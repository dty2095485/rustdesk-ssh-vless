#!/usr/bin/env bash
# Case B retest: nginx killed AFTER conf revert (the race scenario).
set -euo pipefail
NGINX_BIN=/www/server/nginx/sbin/nginx
CONF=/www/server/panel/vhost/nginx/your-domain.example.conf

install -m 755 /tmp/fix_vless_mux.sh /root/fix_vless_mux.sh
echo '--- immediate repair/start (nginx currently down) ---'
bash /root/fix_vless_mux.sh
sleep 25
pgrep -x nginx >/dev/null && echo "nginx RUNNING pid=$(pgrep -x nginx | head -1)" || echo 'nginx STILL DOWN'
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1

echo '===== CASE B RACE: revert then kill nginx 1s later ====='
sed -i 's/^\(\s*\)listen 127.0.0.1:4443 ssl;$/\1listen 443 ssl;/' "$CONF"
sed -i 's/if (\$server_port = 80) {/if (\$server_port != 443) {/' "$CONF"
(sleep 1; pkill -x nginx) &
sleep 20
grep -n -E 'listen 127.0.0.1:4443|server_port = 80' "$CONF" | head -3
pgrep -x nginx >/dev/null && echo "nginx RUNNING pid=$(pgrep -x nginx | head -1)" || echo 'nginx STILL DOWN'
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1

echo '===== pid file + log ====='
echo "pid file: [$(cat /www/server/nginx/logs/nginx.pid)]"
tail -12 /var/log/vless-mux-fix.log
