#!/usr/bin/env bash
F=/home/dty/.cargo/registry/src/index.crates.io-*/openssl-sys-0.9.117/build/main.rs
sed -n '290,330p' $F
echo '--- vendored logic ---'
grep -n 'vendored\|OPENSSL_NO_VENDOR' $F | head -15
