#!/usr/bin/env bash
# EMERGENCY: rollback nginx to pre-mux state and bring the website back.
set -u
NGINX_BIN=/www/server/nginx/sbin/nginx
VHOST_DIR=/www/server/panel/vhost/nginx

echo '==> who holds 443 (before rollback)'
ss -ltnp | grep ':443' || true
ss -lunp | grep ':443' || true
pgrep -a nginx || true
ls -l /usr/bin/nginx /www/server/nginx/sbin/nginx 2>/dev/null

echo '==> rollback: restore site conf, remove mux'
LATEST_BAK=$(ls -t "$VHOST_DIR"/your-domain.example.conf.vlessbak.* 2>/dev/null | head -1)
if [ -n "$LATEST_BAK" ]; then
  cp "$LATEST_BAK" "$VHOST_DIR/your-domain.example.conf"
  echo "    restored from $LATEST_BAK"
fi
rm -f "$VHOST_DIR/tcp/vless_mux.conf"
grep -n 'listen' "$VHOST_DIR/your-domain.example.conf" | head -4

echo '==> start nginx'
"$NGINX_BIN" -t
"$NGINX_BIN"
sleep 2
ss -ltnp | grep ':443' || true

echo '==> website check'
curl -skI --max-time 10 https://your-domain.example | head -3
