#!/usr/bin/env bash
export PATH=$HOME/.cargo/bin:$HOME/zig:$PATH
cd ~/build
echo '--- required GLIBC versions ---'
readelf --version-info target/x86_64-unknown-linux-gnu/release/hbbs 2>/dev/null | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -3
echo '--- dynamic libs needed ---'
readelf -d target/x86_64-unknown-linux-gnu/release/hbbs 2>/dev/null | grep NEEDED
