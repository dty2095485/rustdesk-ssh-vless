#!/usr/bin/env bash
echo '=== stream dir ==='
ls -la /www/server/nginx/conf/stream/
for f in /www/server/nginx/conf/stream/*.conf; do
  echo "--- $f ---"
  cat "$f"
done
echo '=== vhost tcp dir ==='
cat /www/server/panel/vhost/nginx/tcp/vless_mux.conf
echo '=== who listens 443 in vhosts ==='
grep -rn 'listen 443' /www/server/panel/vhost/nginx/*.conf | head -10
