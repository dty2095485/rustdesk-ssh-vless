#!/usr/bin/env bash
echo '--- nas cert validity ---'
for f in /root/.acme.sh/nas.your-domain.example/fullchain.cer /root/.acme.sh/nas.your-domain.example/nas.your-domain.example.cer; do
  [ -f "$f" ] && echo "== $f" && openssl x509 -in "$f" -noout -subject -dates 2>/dev/null
done
ls /root/.acme.sh/ | head -20
echo '--- nginx.conf includes (stream/tcp) ---'
grep -n -E 'stream|tcp|include' /www/server/nginx/conf/nginx.conf | head -30
echo '--- existing tcp dir contents ---'
ls -la /www/server/panel/vhost/nginx/tcp/ 2>/dev/null
echo '--- your-domain.example.conf (first 45 lines) ---'
head -45 /www/server/panel/vhost/nginx/your-domain.example.conf
echo '--- openssl on vps ---'
command -v openssl || echo '(no openssl)'
echo '--- acme reloadcmd for nas ---'
cat /root/.acme.sh/nas.your-domain.example/nas.your-domain.example.conf 2>/dev/null | grep -i -E 'reload|webroot|acme' | head
