#!/usr/bin/env bash
set -e
BIN="$1"
OUT="$2"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

# 1. Filesystem layer: usr/bin/hbssh
mkdir -p "$STAGE/fs/usr/bin"
cp "$BIN" "$STAGE/fs/usr/bin/hbssh"
chmod 0755 "$STAGE/fs/usr/bin/hbssh"
tar -C "$STAGE/fs" -cf "$STAGE/layer.tar" us
LAYER_ID=$(sha256sum "$STAGE/layer.tar" | cut -d' ' -f1)

# 2. Image config JSON
cat > "$STAGE/config.json" <<EOF
{"architecture":"arm64","os":"linux","config":{"Env":["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"],"Entrypoint":["/usr/bin/hbssh"],"ExposedPorts":{"22/tcp":{}}},"created":"2026-08-16T00:00:00Z","rootfs":{"type":"layers","diff_ids":["sha256:$LAYER_ID"]},"history":[{"created":"2026-08-16T00:00:00Z","created_by":"hbssh offline build"}]}
EOF
CONFIG_ID=$(sha256sum "$STAGE/config.json" | cut -d' ' -f1)
mv "$STAGE/config.json" "$STAGE/$CONFIG_ID.json"

# 3. manifest.json
printf '[{"Config":"%s.json","RepoTags":["hbssh:latest"],"Layers":["%s/layer.tar"]}]\n' "$CONFIG_ID" "$LAYER_ID" > "$STAGE/manifest.json"

# 4. layer directory + final archive
mkdir -p "$STAGE/$LAYER_ID"
cp "$STAGE/layer.tar" "$STAGE/$LAYER_ID/layer.tar"
tar -C "$STAGE" -cf "$OUT" manifest.json "$CONFIG_ID.json" "$LAYER_ID/layer.tar"

echo "IMAGE_TAR=$OUT"
echo "CONFIG_ID=$CONFIG_ID"
echo "LAYER_ID=$LAYER_ID"
