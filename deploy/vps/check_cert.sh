#!/usr/bin/env bash
echo "VPS date: $(date '+%Y-%m-%d %H:%M %Z')"
echo '--- BT panel cert dir ---'
ls -la /www/server/panel/vhost/cert/ 2>/dev/null
echo '--- BT nas cert ---'
if [ -f /www/server/panel/vhost/cert/nas.your-domain.example/fullchain.pem ]; then
  openssl x509 -in /www/server/panel/vhost/cert/nas.your-domain.example/fullchain.pem -noout -subject -dates
else
  echo '(no BT cert for nas.your-domain.example)'
fi
echo '--- acme.sh dirs ---'
ls -d ~/.acme.sh/nas.your-domain.example* 2>/dev/null
for f in ~/.acme.sh/nas.your-domain.example/fullchain.cer ~/.acme.sh/nas.your-domain.example_ecc/fullchain.cer; do
  if [ -f "$f" ]; then
    echo "== $f"
    openssl x509 -in "$f" -noout -subject -dates
  fi
done
echo '--- hbvless env current ---'
cat /etc/rustdesk-vless/hbvless.env 2>/dev/null || echo '(not created yet)'
echo '--- deploy4 leftover state ---'
grep -n 'listen' /www/server/panel/vhost/nginx/your-domain.example.conf | head -4
cat /www/server/panel/vhost/nginx/tcp/vless_mux.conf 2>/dev/null || echo '(no mux yet)'
docker ps -a --format '{{.Names}} | {{.Status}}' | grep -i hbvless || echo '(no hbvless container)'
