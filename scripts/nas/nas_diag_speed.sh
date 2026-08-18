#!/bin/bash
# nas_diag_speed.sh — 诊断"外网拉取文件只有 ~30Mbps"问题
# 用法: 在 NAS 上执行 sh nas_diag_speed.sh
#       如果正在拉文件，再跑一次即可看到实时上行速率
set -u
PASS='Zww3.1415926'
RELAY_PORT=21117

run_sudo() { echo "$PASS" | sudo -S "$@" 2>/dev/null; }

console() { # $1 = hbbr console 命令
  timeout 3 bash -c "exec 3<>/dev/tcp/127.0.0.1/${RELAY_PORT}; printf '%s\n' '$1' >&3; cat <&3" 2>/dev/null
}

echo "===== [1] hbbr 容器实际环境变量 ====="
run_sudo docker inspect hbbr --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(SINGLE_BANDWIDTH|LIMIT_SPEED|TOTAL_BANDWIDTH|DOWNGRADE_THRESHOLD|DOWNGRADE_START_CHECK|VLESS_HBBR)' \
  || echo "  (未读取到 env，容器可能未运行或未设置这些变量)"

echo
echo "===== [2] hbbr 运行中实际限速值 (127.0.0.1:${RELAY_PORT}) ====="
for c in sb tb ls dt t; do
  echo "  $c -> $(console "$c" | head -1)"
done

echo
echo "===== [3] hbbr 近6小时日志: downgrade/blocked ====="
run_sudo docker logs hbbr --since 6h | grep -iE 'downgrade|blocked|blacklist' || echo "  (无相关记录)"

echo
echo "===== [4] NAS 网络出口与实时上行 ====="
IFACE=$(ip route 2>/dev/null | awk '/default/{print $5; exit}')
[ -z "$IFACE" ] && IFACE=$(ls /sys/class/net | grep -vE '^(lo|docker|veth|br-|virbr)' | head -1)
echo "  默认接口: ${IFACE:-未知}"
P1=$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null || echo 0)
sleep 5
P2=$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null || echo 0)
echo "  近5s NAS 上行速率: $(( (P2 - P1) * 8 / 5 / 1000000 )) Mbps  (拉文件时观察是否封顶)"

echo
echo "===== [5] hbssh 当前转发目标(决定 21117 走真实中继还是 source.py) ====="
run_sudo docker inspect hbssh --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^SSH_HBBR' || echo "  (未读取到)"
