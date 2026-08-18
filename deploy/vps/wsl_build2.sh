#!/usr/bin/env bash
export PATH=$HOME/.cargo/bin:$HOME/zig:$PATH
cd ~/build
DATABASE_URL=sqlite:/home/dty/build/db_v2.sqlite3 cargo zigbuild --release --bin hbbs --target x86_64-unknown-linux-gnu.2.17 > /tmp/zb.log 2>&1
echo "exit=$?"
grep -n -A12 'error\[E' /tmp/zb.log | head -40
grep -n -B2 -A18 'panicked' /tmp/zb.log | head -50
grep -n 'error:' /tmp/zb.log | head -10
tail -8 /tmp/zb.log
