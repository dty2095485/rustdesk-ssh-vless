#!/usr/bin/env bash
export PATH=$HOME/.cargo/bin:$HOME/zig:$PATH
cd ~/build
echo '--- who depends on native-tls ---'
cargo tree -i native-tls 2>/dev/null | head -8
echo '--- openssl-sys feature graph ---'
cargo tree -e features -i openssl-sys 2>/dev/null | head -25
echo '--- is vendored in features? ---'
cargo tree -e features 2>/dev/null | grep -i 'vendored' | head -5
