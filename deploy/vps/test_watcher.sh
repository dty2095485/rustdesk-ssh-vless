#!/usr/bin/env bash
# Re-test the watcher with the improved fix script (reload-first).
set -euo pipefail
NGINX_BIN=/www/server/nginx/sbin/nginx
CONF=/www/server/panel/vhost/nginx/your-domain.example.conf

install -m 755 /tmp/fix_vless_mux.sh /root/fix_vless_mux.sh

revert_conf() {
  sed -i 's/^\(\s*\)listen 127.0.0.1:4443 ssl;$/\1listen 443 ssl;/' "$CONF"
  sed -i 's/if (\$server_port = 80) {/if (\$server_port != 443) {/' "$CONF"
}

echo '===== CASE A: panel saves while nginx is running ====='
BEFORE=$(pgrep -x nginx | head -1)
revert_conf
sleep 10
AFTER=$(pgrep -x nginx | head -1)
grep -n -E 'listen 127.0.0.1:4443|server_port' "$CONF" | head -3
echo "master pid before=$BEFORE after=$AFTER (expect same)"
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1

echo '===== CASE B: panel restarts nginx with broken config (nginx goes down) ====='
revert_conf
"$NGINX_BIN" -s quit
for i in $(seq 1 20); do pgrep -x nginx >/dev/null || break; sleep 0.5; done
pgrep -x nginx >/dev/null && { echo 'nginx still up, force stop'; "$NGINX_BIN" -s stop; sleep 2; }
echo "nginx down; waiting for watcher to repair + start..."
sleep 12
grep -n -E 'listen 127.0.0.1:4443|server_port' "$CONF" | head -3
pgrep -x nginx >/dev/null && echo "nginx RUNNING pid=$(pgrep -x nginx | head -1)" || echo 'nginx STILL DOWN'
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1

echo '===== watcher log ====='
tail -8 /var/log/vless-mux-fix.log
