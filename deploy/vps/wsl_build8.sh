#!/usr/bin/env bash
export PATH=$HOME/.cargo/bin:$HOME/zig:$PATH
cd ~/build
DATABASE_URL=sqlite:/home/dty/build/db_v2.sqlite3 cargo zigbuild --release --bin hbbs --target x86_64-unknown-linux-gnu.2.34 > /tmp/zb.log 2>&1 || true
echo '--- result ---'
tail -2 /tmp/zb.log
BIN=target/x86_64-unknown-linux-gnu/release/hbbs
if [ -f "$BIN" ]; then
  readelf --version-info "$BIN" | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -2
  echo '--- NEEDED ---'
  readelf -d "$BIN" | grep NEEDED
  cp "$BIN" /mnt/d/chatgpt/vps-deploy/hbbs-linux && echo COPIED
fi
