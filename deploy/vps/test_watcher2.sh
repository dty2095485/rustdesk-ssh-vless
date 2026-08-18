#!/usr/bin/env bash
# Final watcher test: Case A (running nginx) + Case B (nginx down), using signals.
set -euo pipefail
NGINX_BIN=/www/server/nginx/sbin/nginx
CONF=/www/server/panel/vhost/nginx/your-domain.example.conf

install -m 755 /tmp/fix_vless_mux.sh /root/fix_vless_mux.sh
bash /root/fix_vless_mux.sh

revert_conf() {
  sed -i 's/^\(\s*\)listen 127.0.0.1:4443 ssl;$/\1listen 443 ssl;/' "$CONF"
  sed -i 's/if (\$server_port = 80) {/if (\$server_port != 443) {/' "$CONF"
}

echo '===== CASE A: panel saves while nginx runs ====='
BEFORE=$(pgrep -x nginx | head -1)
revert_conf
sleep 10
AFTER=$(pgrep -x nginx | head -1)
grep -n -E 'listen 127.0.0.1:4443|server_port = 80' "$CONF" | head -3
echo "master before=$BEFORE after=$AFTER (expect same = zero downtime)"
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1

echo '===== CASE B: panel full-restarts nginx with broken config ====='
revert_conf
pkill -QUIT -x nginx || true
for i in $(seq 1 20); do pgrep -x nginx >/dev/null || break; sleep 0.5; done
pkill -x nginx 2>/dev/null || true
sleep 1
echo "nginx down (pgrep: $(pgrep -x nginx | wc -l)); waiting for watcher..."
sleep 12
grep -n -E 'listen 127.0.0.1:4443|server_port = 80' "$CONF" | head -3
pgrep -x nginx >/dev/null && echo "nginx RUNNING pid=$(pgrep -x nginx | head -1)" || echo 'nginx STILL DOWN'
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1

echo '===== pid file + watcher log ====='
echo "pid file: [$(cat /www/server/nginx/logs/nginx.pid)]"
tail -10 /var/log/vless-mux-fix.log
