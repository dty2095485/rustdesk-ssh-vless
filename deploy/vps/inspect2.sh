#!/usr/bin/env bash
echo '--- serving nginx binary ---'
readlink /proc/3067461/exe
readlink /proc/3879853/exe
echo '--- nginx -V of serving binary ---'
SERVING=$(readlink /proc/3067461/exe)
"$SERVING" -V 2>&1 | tr ' ' '\n' | grep -E 'stream|preread' || echo '(no stream modules!)'
echo '--- nginx conf layout ---'
"$SERVING" -t 2>&1
echo '--- bt nginx vhosts ---'
ls /www/server/panel/vhost/nginx/ 2>/dev/null
echo '--- site 443 config (detian) ---'
grep -rn -E 'listen.*443|ssl_certificate |server_name' /www/server/panel/vhost/nginx/ 2>/dev/null | grep -i detian | head -20
grep -rn -E 'listen.*443|ssl_certificate |server_name' /etc/nginx/conf.d/ /etc/nginx/nginx.conf 2>/dev/null | head -20
echo '--- acme.sh / certbot ---'
ls -d ~/.acme.sh 2>/dev/null && ls ~/.acme.sh/*.your-domain.example 2>/dev/null | head
command -v certbot acme.sh || true
echo '--- rustdesk container inspect ---'
docker inspect rustdesk_rrsc-rustdesk_rrsC-1 --format '{{json .Config.Env}}' 2>/dev/null
echo
docker inspect rustdesk_rrsc-rustdesk_rrsC-1 --format '{{json .Config.Cmd}}' 2>/dev/null
echo
echo '--- website reachable from inside ---'
curl -skI https://your-domain.example --max-time 10 | head -5
echo '--- ports 21116/21117 via loopback ---'
timeout 3 bash -c '</dev/tcp/127.0.0.1/21116 && echo 21116_OPEN' || echo 21116_CLOSED
timeout 3 bash -c '</dev/tcp/127.0.0.1/21117 && echo 21117_OPEN' || echo 21117_CLOSED
