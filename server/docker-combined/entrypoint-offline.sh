#!/bin/sh
# Minimal supervisor for the combined image, used by the daemon-free
# (crane-assembled) build in build-offline-image.sh. Mirrors the per-service
# logic in rootfs/etc/s6-overlay/s6-rc.d/*/run, but without s6-overlay's
# automatic restart/readiness features: if one service dies, all are killed
# and the container exits so an external restart policy can recover.
set -eu

mkdir -p /data
cd /data

if [ ! -f /data/id_ed25519.pub ] && [ -r /run/secrets/key_pub ]; then
    cp /run/secrets/key_pub /data/id_ed25519.pub
fi
if [ ! -f /data/id_ed25519 ] && [ -r /run/secrets/key_priv ]; then
    cp /run/secrets/key_priv /data/id_ed25519
fi
if [ -f /data/id_ed25519.pub ] && [ ! -f /data/id_ed25519 ]; then
    echo "RustDesk private key is missing" >&2
    exit 1
fi
if [ ! -f /data/id_ed25519.pub ] && [ -f /data/id_ed25519 ]; then
    echo "RustDesk public key is missing" >&2
    exit 1
fi
if [ -f /data/id_ed25519.pub ] && [ -f /data/id_ed25519 ]; then
    chmod 0600 /data/id_ed25519.pub /data/id_ed25519
    /usr/bin/rustdesk-utils validatekeypair \
        "$(cat /data/id_ed25519.pub)" "$(cat /data/id_ed25519)"
fi

: "${RELAY:?Set RELAY to the public RustDesk relay host and port}"

pids=""
trap 'kill $pids 2>/dev/null; wait; exit 0' TERM INT

set -- /usr/bin/hbbs -r "$RELAY"
[ "${ENCRYPTED_ONLY:-0}" = "1" ] && set -- "$@" -k _
"$@" & pids="$pids $!"

set -- /usr/bin/hbbr
[ "${ENCRYPTED_ONLY:-0}" = "1" ] && set -- "$@" -k _
"$@" & pids="$pids $!"

if [ -n "${VLESS_UUID:-}" ] && [ -n "${VLESS_CERT:-}" ] && [ -n "${VLESS_KEY:-}" ]; then
    if [ -r "$VLESS_CERT" ] && [ -r "$VLESS_KEY" ]; then
        /usr/bin/hbvless & pids="$pids $!"
    else
        echo "VLESS_CERT/VLESS_KEY not readable, skipping hbvless" >&2
    fi
else
    echo "VLESS_UUID/VLESS_CERT/VLESS_KEY not set, skipping hbvless" >&2
fi

/usr/bin/hbssh & pids="$pids $!"

wait -n
kill $pids 2>/dev/null
wait
