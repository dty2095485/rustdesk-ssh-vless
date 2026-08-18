#!/bin/sh
set -eu

: "${RUSTDESK_KEY:?Set RUSTDESK_KEY}"
: "${RELAY:?Set RELAY to the NAS public RustDesk relay address}"

cd /data
PIDS=""

stop_all() {
  for pid in $PIDS; do
    kill "$pid" 2>/dev/null || true
  done
  wait || true
}
trap 'stop_all; exit 0' INT TERM

/usr/bin/hbbr -k "$RUSTDESK_KEY" &
PIDS="$PIDS $!"
/usr/bin/hbbs -k "$RUSTDESK_KEY" -r "$RELAY" &
PIDS="$PIDS $!"
/usr/bin/hbssh &
PIDS="$PIDS $!"

if [ "${VLESS_ENABLED:-0}" = "1" ]; then
  : "${VLESS_UUID:?Set VLESS_UUID when VLESS_ENABLED=1}"
  : "${VLESS_CERT:?Set VLESS_CERT when VLESS_ENABLED=1}"
  : "${VLESS_KEY:?Set VLESS_KEY when VLESS_ENABLED=1}"
  test -r "$VLESS_CERT"
  test -r "$VLESS_KEY"
  /usr/bin/hbvless &
  PIDS="$PIDS $!"
else
  echo "hbvless is installed but disabled (set VLESS_ENABLED=1 with TLS settings to enable it)"
fi

while :; do
  for pid in $PIDS; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "A RustDesk service exited; restarting the container" >&2
      stop_all
      exit 1
    fi
  done
  sleep 5
done
