#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
IMAGE_TAG=${IMAGE_TAG:-rustdesk-server-combined:canary}

docker build \
    --file "$SCRIPT_DIR/Dockerfile" \
    --tag "$IMAGE_TAG" \
    "$REPO_DIR"

echo "Built $IMAGE_TAG"

