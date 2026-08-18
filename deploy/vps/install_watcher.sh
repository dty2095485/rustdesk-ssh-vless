#!/usr/bin/env bash
# Install the auto-repair watcher (systemd path unit) for the BT panel rewrite.
set -euo pipefail

echo '==> [1] install new fix script'
install -m 755 /tmp/fix_vless_mux.sh /root/fix_vless_mux.sh

echo '==> [2] install systemd units'
cat > /etc/systemd/system/rustdesk-mux-fix.service <<'EOF'
[Unit]
Description=Re-apply VLESS SNI mux after BT panel rewrites site conf

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 2
ExecStart=/bin/bash /root/fix_vless_mux.sh
EOF
cat > /etc/systemd/system/rustdesk-mux-fix.path <<'EOF'
[Unit]
Description=Watch your-domain.example site conf for BT panel rewrites

[Path]
PathChanged=/www/server/panel/vhost/nginx/your-domain.example.conf

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now rustdesk-mux-fix.path

echo '==> [3] simulate a BT panel save (revert listen + redirect)'
cp /www/server/panel/vhost/nginx/your-domain.example.conf /tmp/your-domain.example.conf.testbak
sed -i 's/^\(\s*\)listen 127.0.0.1:4443 ssl;$/\1listen 443 ssl;/' /www/server/panel/vhost/nginx/your-domain.example.conf
sed -i 's/if (\$server_port = 80) {/if (\$server_port != 443) {/' /www/server/panel/vhost/nginx/your-domain.example.conf
echo '    reverted (simulating panel); waiting for watcher...'
sleep 10

echo '==> [4] verify auto-repair'
grep -n -E 'listen|server_port' /www/server/panel/vhost/nginx/your-domain.example.conf | head -6
ss -ltnp | grep -E ':(443|4443|8443)\s' || true
curl -skI --max-time 10 https://your-domain.example | head -1
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
echo '--- watcher log ---'
cat /var/log/vless-mux-fix.log 2>/dev/null | tail -5
echo '--- unit state ---'
systemctl --no-pager --lines=3 status rustdesk-mux-fix.path | head -6
