#!/usr/bin/env bash
echo '--- effective config: listen/proxy/map lines ---'
/www/server/nginx/sbin/nginx -T 2>/dev/null | grep -nE 'listen |proxy_pass|ssl_preread|map |vless_backend|server_name' | head -50
echo '--- tcp include dir perms ---'
ls -la /www/server/panel/vhost/nginx/tcp/
echo '--- listeners 443/8443 ---'
ss -ltnp | grep -E ':(443|8443)\s' || true
echo '--- direct hbvless 8443 (expect nas cert) ---'
echo Q | openssl s_client -connect 127.0.0.1:8443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=|issuer=|error' | head -3
echo '--- mux 443 with nas SNI ---'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=|issuer=' | head -2
echo '--- nginx error log tail ---'
tail -15 /www/wwwlogs/nginx_error.log 2>/dev/null || tail -15 /www/wwwlogs/error.log 2>/dev/null || echo '(no error log found)'
echo '--- hbvless logs ---'
docker logs --tail 15 hbvless 2>&1 || true
