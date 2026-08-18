#!/usr/bin/env bash
export PATH=$HOME/.cargo/bin:$HOME/zig:$PATH
F=$(ls -d /home/dty/.cargo/registry/src/index.crates.io-*/libsodium-sys-0.2.7/build.rs | head -1)
sed -i 's/let make_arg = if cross_compiling { "all" } else { "check" };/let make_arg = "all";/' "$F"
grep -n 'make_arg' "$F" | head -2
cd ~/build
DATABASE_URL=sqlite:/home/dty/build/db_v2.sqlite3 cargo zigbuild --release --bin hbbs --target x86_64-unknown-linux-gnu.2.17 > /tmp/zb.log 2>&1 || true
echo '--- result ---'
tail -3 /tmp/zb.log
ls -la target/x86_64-unknown-linux-gnu/release/hbbs 2>/dev/null && cp target/x86_64-unknown-linux-gnu/release/hbbs /mnt/d/chatgpt/vps-deploy/hbbs-linux && echo COPIED
