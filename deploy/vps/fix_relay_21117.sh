#!/usr/bin/env bash
# Port-model fix: external = 443 + 21115-21119 only.
# 1) announce relay on 21117 (direct range) instead of 8443
# 2) ENCRYPTED_ONLY=0 -> hbbr runs keyless and accepts official iOS
#    (iOS has no key field; its licence_key fallback is RS_PUB_KEY)
# 3) drop the external 8443 -> 21117 relay mapping
set -euo pipefail
COMPOSE_DIR=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC
COMPOSE=$COMPOSE_DIR/docker-compose.yml
cd "$COMPOSE_DIR"

cp "$COMPOSE" "$COMPOSE.bak.$(date +%s)"

sed -i 's|- RELAY=.*|- RELAY=your-domain.example:21117|' "$COMPOSE"
sed -i 's|- ENCRYPTED_ONLY=1|- ENCRYPTED_ONLY=0|' "$COMPOSE"
sed -i '\|${HOST_IP}:8443:21117|d' "$COMPOSE"

echo '==> compose after patch:'
grep -nE 'RELAY|ENCRYPTED_ONLY|8443|21117' "$COMPOSE"

echo '==> recreate'
docker compose up -d 2>&1 | tail -3
sleep 10
docker ps --format '{{.Names}} | {{.Status}}'
docker ps --format '{{.Names}} | {{.Ports}}' | grep -i rustdesk

echo '==> key/relay evidence'
docker logs --tail 60 rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -aE 'Key:|Private key|Relay' | head -15

echo '==> listening ports'
ss -ltnp | grep -E ':(8443|21117)\s' | head -5
