#!/usr/bin/env bash
echo '--- hbvless container ---'
docker ps -a --format '{{.Names}} | {{.Status}}' | grep -i hbvless || echo '(no hbvless container!)'
echo '--- hbvless logs ---'
docker logs --tail 15 hbvless 2>&1 || true
echo '--- 8443 listener ---'
ss -ltnp | grep ':8443' || echo '(nothing on 8443)'
echo '--- nas SNI via mux ---'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>&1 | grep -E 'subject=|issuer=|error|refused' | head -5
echo '--- direct 8443 ---'
echo Q | openssl s_client -connect 127.0.0.1:8443 -servername nas.your-domain.example 2>&1 | grep -E 'subject=|error|refused' | head -3
echo '--- mux conf on disk ---'
cat /www/server/panel/vhost/nginx/tcp/vless_mux.conf 2>/dev/null || echo '(missing!)'
