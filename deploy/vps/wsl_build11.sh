#!/usr/bin/env bash
export PATH=$HOME/.cargo/bin:$HOME/zig:$PATH
cd ~/build
cp /mnt/d/chatgpt/rustdesk-server/src/rendezvous_server.rs src/rendezvous_server.rs
cp /mnt/d/chatgpt/rustdesk-server/src/relay_server.rs src/relay_server.rs
cp /mnt/d/chatgpt/rustdesk-server/src/vless.rs src/vless.rs
DATABASE_URL=sqlite:/home/dty/build/db_v2.sqlite3 cargo zigbuild --release --bin hbbs --bin hbbr --bin hbvless --target x86_64-unknown-linux-gnu.2.34 > /tmp/zb.log 2>&1 || true
tail -2 /tmp/zb.log
BIN=target/x86_64-unknown-linux-gnu/release
[ -f "$BIN/hbbs" ] && cp "$BIN/hbbs" /mnt/d/chatgpt/vps-deploy/hbbs-linux && echo HBB_COPIED
[ -f "$BIN/hbbr" ] && cp "$BIN/hbbr" /mnt/d/chatgpt/vps-deploy/hbbr-linux && echo HBBR_COPIED
[ -f "$BIN/hbvless" ] && cp "$BIN/hbvless" /mnt/d/chatgpt/vps-deploy/hbvless-linux && echo HBVLESS_COPIED
