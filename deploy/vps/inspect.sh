#!/usr/bin/env bash
echo "SSH_OK"
echo "arch: $(uname -m)"
grep PRETTY_NAME /etc/os-release
echo '--- listeners on 80/443 ---'
ss -ltnp | grep -E ':(80|443)\s' || echo '(none)'
echo '--- web servers ---'
for c in nginx caddy haproxy httpd; do
  command -v $c || true
done
echo '--- bt panel ---'
ls -d /www/server 2>/dev/null || echo '(no /www/server)'
echo '--- nginx modules (if nginx found) ---'
NGINX=$(command -v nginx || echo /www/server/nginx/sbin/nginx)
[ -x "$NGINX" ] && "$NGINX" -V 2>&1 | tr ' ' '\n' | grep -E 'stream|preread' || echo '(nginx not found)'
echo '--- docker ---'
docker ps --format '{{.Names}} | {{.Ports}}' 2>/dev/null | head -20 || echo '(no docker)'
echo '--- dns check (from vps) ---'
getent hosts nas.your-domain.example || echo '(nas.your-domain.example not resolved)'
getent hosts fnos.your-domain.example || echo '(fnos.your-domain.example not resolved)'
getent hosts your-domain.example || echo '(your-domain.example not resolved)'
