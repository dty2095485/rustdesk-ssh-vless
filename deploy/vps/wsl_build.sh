#!/usr/bin/env bash
set -e
export PATH=$HOME/.cargo/bin:$HOME/zig:$PATH
cd ~/build
grep -q '^native-tls' Cargo.toml || sed -i '/^rustls-pemfile = /a native-tls = { version = "0.2", features = ["vendored"] }' Cargo.toml
grep -n 'native-tls\|rustls-pemfile' Cargo.toml | head -4
DATABASE_URL=sqlite:/home/dty/build/db_v2.sqlite3 cargo zigbuild --release --bin hbbs --target x86_64-unknown-linux-gnu.2.17 2>&1 | tail -3
ls -la target/x86_64-unknown-linux-gnu/release/hbbs
cp target/x86_64-unknown-linux-gnu/release/hbbs /mnt/d/chatgpt/vps-deploy/hbbs-linux
echo COPIED
