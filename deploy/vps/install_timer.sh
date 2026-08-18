#!/usr/bin/env bash
# Install the periodic watchdog timer + bring nginx up + full verification.
set -euo pipefail

echo '==> [1] watchdog timer (every 2 min, self-heal any nginx death)'
cat > /etc/systemd/system/rustdesk-mux-fix.timer <<'EOF'
[Unit]
Description=Periodic self-heal watchdog for nginx VLESS mux

[Timer]
OnBootSec=90s
OnUnitActiveSec=120s

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now rustdesk-mux-fix.timer

echo '==> [2] immediate repair (nginx currently down)'
bash /root/fix_vless_mux.sh
sleep 3

echo '==> [3] verification'
pgrep -x nginx >/dev/null && echo "nginx RUNNING pid=$(pgrep -x nginx | head -1)" || echo 'nginx STILL DOWN'
ss -ltnp | grep -E ':(443|4443|8443)\s' || true
echo '--- website ---'
curl -skI --max-time 10 https://your-domain.example | head -1
echo '--- nas SNI (VLESS entry) ---'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
echo '--- detian SNI (website) ---'
echo Q | openssl s_client -connect 127.0.0.1:443 -servername your-domain.example 2>/dev/null | grep -E 'subject=' | head -1
echo '--- hbvless container ---'
docker ps --format '{{.Names}} | {{.Status}}' | grep hbvless

echo '==> [4] timer state'
systemctl --no-pager --lines=3 status rustdesk-mux-fix.timer | head -5
