#!/usr/bin/env bash
export PATH=$HOME/.cargo/bin:$HOME/zig:$PATH
cd ~/build
rm -rf target/release/build/libsodium-sys-* target/x86_64-unknown-linux-gnu/release/build/libsodium-sys-*
DATABASE_URL=sqlite:/home/dty/build/db_v2.sqlite3 cargo zigbuild --release --bin hbbs --target x86_64-unknown-linux-gnu.2.17 > /tmp/zb.log 2>&1 || true
echo '--- result ---'
grep -n 'error\|panicked' /tmp/zb.log | head -8
tail -3 /tmp/zb.log
ls -la target/x86_64-unknown-linux-gnu/release/hbbs 2>/dev/null && cp target/x86_64-unknown-linux-gnu/release/hbbs /mnt/d/chatgpt/vps-deploy/hbbs-linux && echo COPIED
