#!/usr/bin/env bash
# RustDesk VLESS deployment (hbbs + hbbr on 127.0.0.1, hbvless on 0.0.0.0:443).
# Usage: bash deploy.sh <domain>
set -euo pipefail

DOMAIN="${1:?usage: deploy.sh <domain>}"
TARBALL=/tmp/rv.tar.gz
EXTRACT=/tmp/rv
INSTALL_DIR=/opt/rustdesk-vless
CONF_DIR=/etc/rustdesk-vless

echo "==> OS info"
. /etc/os-release
echo "    $PRETTY_NAME / $(uname -m)"

if [ "$(uname -m)" != "x86_64" ]; then
  echo "ERROR: release binaries are x86_64 only" >&2
  exit 1
fi

echo "==> Installing files"
[ -f "$TARBALL" ] || { echo "ERROR: $TARBALL missing, upload it first" >&2; exit 1; }
rm -rf "$EXTRACT"; mkdir -p "$EXTRACT"
tar -xzf "$TARBALL" -C "$EXTRACT" --strip-components=1
install -d -m 755 "$INSTALL_DIR" "$CONF_DIR"
install -m 755 "$EXTRACT/hbbs" "$EXTRACT/hbbr" "$EXTRACT/hbvless" "$INSTALL_DIR/"
install -m 644 "$EXTRACT/systemd/"*.service /etc/systemd/system/

echo "==> Writing env (generating UUID)"
UUID=$(cat /proc/sys/kernel/random/uuid)
umask 077
cat > "$CONF_DIR/hbvless.env" <<EOF
VLESS_UUID=$UUID
VLESS_LISTEN=0.0.0.0:443
VLESS_CERT=/etc/letsencrypt/live/$DOMAIN/fullchain.pem
VLESS_KEY=/etc/letsencrypt/live/$DOMAIN/privkey.pem
VLESS_HBBS=127.0.0.1:21116
VLESS_HBBR=127.0.0.1:21117
EOF
echo "$UUID" > "$CONF_DIR/uuid.txt"
chmod 600 "$CONF_DIR/hbvless.env" "$CONF_DIR/uuid.txt"

echo "==> Hardening units: bind hbbs/hbbr to loopback, set real domain"
sed -i "s|^ExecStart=.*hbbs .*|ExecStart=$INSTALL_DIR/hbbs -b 127.0.0.1 -r $DOMAIN:21117|" /etc/systemd/system/rustdesk-hbbs.service
sed -i "s|^ExecStart=.*hbbr.*|ExecStart=$INSTALL_DIR/hbbr -b 127.0.0.1|" /etc/systemd/system/rustdesk-hbbr.service

echo "==> Starting hbbs + hbbr"
systemctl daemon-reload
systemctl enable --now rustdesk-hbbs rustdesk-hbbr
sleep 2
systemctl --no-pager --lines=5 status rustdesk-hbbs || true
ss -ltnp | grep -E '21115|21116|21117|21118' || true

echo "==> Issuing Let's Encrypt certificate for $DOMAIN"
if ! command -v certbot >/dev/null 2>&1; then
  case "$ID" in
    debian|ubuntu) apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq certbot ;;
    rhel|centos|fedora|rocky|almalinux) dnf install -y -q certbot ;;
    *) echo "ERROR: install certbot manually for $ID" >&2; exit 1 ;;
  esac
fi
if ! certbot certonly --standalone --non-interactive --agree-tos \
      --register-unsafely-without-email -d "$DOMAIN" \
      --cert-name "$DOMAIN"; then
  echo "    http-01 failed, falling back to tls-alpn (443 must be free)"
  certbot certonly --standalone --preferred-challenges tls-alpn \
      --non-interactive --agree-tos --register-unsafely-without-email \
      -d "$DOMAIN" --cert-name "$DOMAIN"
fi

echo "==> Renewal hook: restart hbvless after cert renewal"
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/restart-rustdesk.sh <<'EOF'
#!/bin/sh
systemctl try-restart rustdesk-hbvless
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/restart-rustdesk.sh

echo "==> Starting hbvless"
systemctl enable --now rustdesk-hbvless
sleep 2
systemctl --no-pager --lines=5 status rustdesk-hbvless || true
ss -ltnp | grep ':443 ' || true

echo "==> DEPLOYED"
echo "    domain: $DOMAIN"
echo "    uuid:   $(cat "$CONF_DIR/uuid.txt")"
