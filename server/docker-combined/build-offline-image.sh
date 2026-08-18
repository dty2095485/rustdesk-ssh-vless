#!/usr/bin/env bash
# Daemon-free image build: assembles the combined hbbs+hbbr+hbvless+hbssh
# image and pushes it straight to a registry using crane
# (github.com/google/go-containerregistry), without needing a local Docker
# daemon. Extends the single-binary offline-tar trick in
# ../../hbssh-deploy/make-image.sh to a full multi-binary image with a real
# base OS (for glibc + ca-certificates) instead of hand-writing OCI JSON.
#
# Usage: build-offline-image.sh <path-to-release-bin-dir> <target-image-ref>
# Example:
#   build-offline-image.sh target/release ghcr.io/USER/rustdesk-server-combined:latest
set -euo pipefail

BIN_DIR="${1:?Usage: $0 <release-bin-dir> <target-image-ref>}"
IMAGE_REF="${2:?Usage: $0 <release-bin-dir> <target-image-ref>}"
BASE_IMAGE="${BASE_IMAGE:-ubuntu:26.04}"
CRANE="${CRANE:-crane}"

for bin in hbbs hbbr hbvless hbssh rustdesk-utils; do
    [ -x "$BIN_DIR/$bin" ] || { echo "missing $BIN_DIR/$bin (build it first)" >&2; exit 1; }
done

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/layer/usr/bin"
for bin in hbbs hbbr hbvless hbssh rustdesk-utils; do
    cp "$BIN_DIR/$bin" "$STAGE/layer/usr/bin/$bin"
done
cp "$(dirname "$0")/entrypoint-offline.sh" "$STAGE/layer/usr/bin/entrypoint.sh"
chmod 0755 "$STAGE/layer/usr/bin/"*

tar -C "$STAGE/layer" -cf "$STAGE/layer.tar" usr

# 1. Append the binaries layer onto the base image, entirely offline
#    (-o writes a local docker-style tarball, no registry access needed yet).
echo "Assembling layer on top of $BASE_IMAGE (offline) ..."
"$CRANE" append -b "$BASE_IMAGE" -f "$STAGE/layer.tar" -t "${IMAGE_REF}-base" -o "$STAGE/combined.tar"

# 2. Push the intermediate image so `crane mutate` (which only operates on
#    registry references, not local tarballs) has something to point at.
echo "Pushing intermediate image ..."
"$CRANE" push "$STAGE/combined.tar" "${IMAGE_REF}-base"

# 3. Set entrypoint/workdir/env on the pushed image, writing the real tag.
echo "Setting entrypoint/config and publishing $IMAGE_REF ..."
"$CRANE" mutate "${IMAGE_REF}-base" \
    --entrypoint /usr/bin/entrypoint.sh \
    -w /data \
    -e RELAY= \
    -e ENCRYPTED_ONLY=0 \
    -e VLESS_UUID= \
    -e VLESS_CERT= \
    -e VLESS_KEY= \
    -t "$IMAGE_REF"

echo "Done: $IMAGE_REF"
