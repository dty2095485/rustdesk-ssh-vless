#!/usr/bin/env bash
export PATH=$HOME/.cargo/bin:$HOME/zig:$PATH
cd ~/build
DATABASE_URL=sqlite:/home/dty/build/db_v2.sqlite3 cargo zigbuild --release --bin hbbs --target x86_64-unknown-linux-gnu.2.17 > /tmp/zb.log 2>&1 || true
echo '--- error lines ---'
grep -n 'error\|panicked\|failed to run' /tmp/zb.log | head -12
echo '--- context of first panic ---'
grep -n -A14 'panicked' /tmp/zb.log | head -30
echo '--- tail ---'
tail -6 /tmp/zb.log
ls -la target/x86_64-unknown-linux-gnu/release/hbbs 2>/dev/null && cp target/x86_64-unknown-linux-gnu/release/hbbs /mnt/d/chatgpt/vps-deploy/hbbs-linux && echo COPIED
