#!/usr/bin/env bash
set -e
export PATH=$HOME/.cargo/bin:$HOME/zig:$PATH
cd ~/build
grep -q '^native-tls' Cargo.toml || sed -i '/^rustls-pemfile = /a native-tls = { version = "0.2", features = ["vendored"] }' Cargo.toml
grep -n 'build-dependencies' Cargo.toml | head -2
awk '/^\[build-dependencies\]/{print; print "native-tls = { version = \"0.2\", features = [\"vendored\"] }"; found=1; next} 1; END{if(!found) print "\n[build-dependencies]\nnative-tls = { version = \"0.2\", features = [\"vendored\"] }"}' Cargo.toml > /tmp/ct.tmp && mv /tmp/ct.tmp Cargo.toml
grep -n -A2 'build-dependencies' Cargo.toml | head -6
DATABASE_URL=sqlite:/home/dty/build/db_v2.sqlite3 cargo zigbuild --release --bin hbbs --target x86_64-unknown-linux-gnu.2.17 > /tmp/zb.log 2>&1 && echo BUILD_OK || echo BUILD_FAIL
tail -3 /tmp/zb.log
ls -la target/x86_64-unknown-linux-gnu/release/hbbs 2>/dev/null && cp target/x86_64-unknown-linux-gnu/release/hbbs /mnt/d/chatgpt/vps-deploy/hbbs-linux && echo COPIED
