#!/bin/sh
set -eu

image='rustdesk-combined:1.1.17-arm64-ssh'
name='rustdesk-combined-arm64'
data='/vol2/rustdesk/hbbs'
backup='/vol2/rustdesk/backup-before-combined-arm64'

test ! -e "$backup" || { echo "Backup path already exists: $backup" >&2; exit 1; }
if docker ps -a --format '{{.Names}}' | grep -qxE 'hbbs-precombined|hbbr-precombined|hbssh-precombined'; then
  echo 'Previous rollback containers still exist' >&2
  exit 1
fi

key="$(docker inspect hbbs --format '{{index .Config.Cmd 2}}')"
relay="$(docker inspect hbbs --format '{{index .Config.Cmd 4}}')"
test -n "$key"
test -n "$relay"

mkdir -p "$backup"
docker inspect hbbs hbbr hbssh > "$backup/containers.json"
cp -a "$data" "$backup/data"

rollback() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker rename hbbs-precombined hbbs >/dev/null 2>&1 || true
  docker rename hbbr-precombined hbbr >/dev/null 2>&1 || true
  docker rename hbssh-precombined hbssh >/dev/null 2>&1 || true
  docker start hbbs hbbr hbssh >/dev/null 2>&1 || true
}

docker stop hbbs hbbr hbssh
docker rename hbbs hbbs-precombined
docker rename hbbr hbbr-precombined
docker rename hbssh hbssh-precombined

if ! docker run -d --name "$name" --network host --restart unless-stopped \
  -v "$data:/data" \
  -e "RUSTDESK_KEY=$key" \
  -e "RELAY=$relay" \
  -e VLESS_ENABLED=0 \
  "$image"; then
  rollback
  exit 1
fi

sleep 5
if ! docker ps --format '{{.Names}} {{.Status}}' | grep -q "^$name Up"; then
  rollback
  exit 1
fi
for port in 21115 21116 21117 2222; do
  if ! ss -ltn | grep -q ":$port "; then
    rollback
    exit 1
  fi
done

echo 'NAS ARM64 combined RustDesk is running. VLESS is installed but disabled until TLS settings are supplied.'
