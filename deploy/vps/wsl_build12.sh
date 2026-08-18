#!/usr/bin/env bash
# Fixed clean PATH (Windows PATH contains spaces/parens and breaks `export`).
# Build all three bins; copy outputs only on success.
set -e -o pipefail
export PATH=/home/dty/.cargo/bin:/home/dty/zig:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
cd /home/dty/build
cp /mnt/d/chatgpt/rustdesk-server/src/rendezvous_server.rs src/rendezvous_server.rs
cp /mnt/d/chatgpt/rustdesk-server/src/relay_server.rs src/relay_server.rs
cp /mnt/d/chatgpt/rustdesk-server/src/vless.rs src/vless.rs
DATABASE_URL=sqlite:/home/dty/build/db_v2.sqlite3 cargo zigbuild --release --bin hbbs --bin hbbr --bin hbvless --target x86_64-unknown-linux-gnu.2.34 2>&1 | tail -6
BIN=target/x86_64-unknown-linux-gnu/release
cp "$BIN/hbbs" /mnt/d/chatgpt/vps-deploy/hbbs-linux && echo HBB_COPIED
cp "$BIN/hbbr" /mnt/d/chatgpt/vps-deploy/hbbr-linux && echo HBBR_COPIED
cp "$BIN/hbvless" /mnt/d/chatgpt/vps-deploy/hbvless-linux && echo HBVLESS_COPIED
