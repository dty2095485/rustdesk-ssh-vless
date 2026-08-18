#!/usr/bin/env bash
echo '--- nginx.conf lines 5-30 ---'
sed -n '5,30p' /www/server/nginx/conf/nginx.conf
echo '--- stream conf dir ---'
ls -la /www/server/nginx/conf/stream/ 2>/dev/null
for f in /www/server/nginx/conf/stream/*.conf; do
  echo "== $f"; cat "$f"
done
echo '--- what nas.your-domain.example serves now (from inside) ---'
curl -skI --max-time 10 https://nas.your-domain.example | head -8
echo '--- wwwroot dirs ---'
ls -d /www/wwwroot/* 2>/dev/null
echo '--- nas webroot exists? ---'
ls -la /www/wwwroot/nas.your-domain.example 2>/dev/null | head
echo '--- frps processes / ports ---'
ss -ltnp | grep -vE ':(80|443|22|8888|888|21115|21116|21117|21118|21119)\s' | head -20
ps aux | grep -i frp | grep -v grep | head -5
echo '--- 0.default.conf head ---'
head -12 /www/server/panel/vhost/nginx/0.default.conf 2>/dev/null
