#!/usr/bin/env bash
export PATH=$HOME/.cargo/bin:$HOME/zig:$PATH
cd ~/build
echo '--- openssl-sys section of last log ---'
grep -n 'openssl-sys' /tmp/zb.log | head -5
sed -n '/Compiling openssl-sys/,/error:/p' /tmp/zb.log | head -40
echo '--- vendored markers? ---'
grep -n -iE 'vendored|Configure|Building OpenSSL|openssl-3' /tmp/zb.log | head -10
