#!/usr/bin/env bash
# Graceful full nginx restart so stream(0.0.0.0:443) + http(127.0.0.1:443) bind cleanly.
set -euo pipefail
NGINX_BIN=/www/server/nginx/sbin/nginx

echo '==> graceful quit'
"$NGINX_BIN" -s quit
for i in $(seq 1 20); do
  pgrep -x nginx >/dev/null || break
  sleep 0.5
done
pgrep -x nginx >/dev/null && { echo 'still running, force stop'; "$NGINX_BIN" -s stop; sleep 2; }

echo '==> start'
"$NGINX_BIN"
sleep 2
"$NGINX_BIN" -t

echo '==> listeners'
ss -ltnp | grep -E ':(80|443|8443)\s' || true

echo '==> website (public path through mux)'
curl -skI --max-time 10 https://your-domain.example | head -3

echo '==> nas SNI through mux (expect nas.your-domain.example cert)'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=|issuer=' | head -2

echo '==> detian SNI through mux (expect detian cert, website still served)'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
