IFACE=$(ip route 2>/dev/null | awk '/default/{print $5; exit}')
[ -z "$IFACE" ] && IFACE=$(ls /sys/class/net | grep -vE '^(lo|docker|veth|br-|virbr)' | head -1)
echo "MONITOR interface=$IFACE start=$(date +%s)"
PREV=$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null)
MAX=0
for i in $(seq 1 300); do
  sleep 1
  CUR=$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null)
  RATE=$(( (CUR - PREV) * 8 / 1000000 ))
  PREV=$CUR
  [ "$RATE" -gt "$MAX" ] && MAX=$RATE
  echo "t=$i tx=${RATE}Mbps max=${MAX}Mbps"
done
echo "MONITOR_DONE max=${MAX}Mbps"
