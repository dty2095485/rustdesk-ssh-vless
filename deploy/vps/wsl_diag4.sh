#!/usr/bin/env bash
F=$(ls -d /home/dty/.cargo/registry/src/index.crates.io-*/libsodium-sys-0.2.7/build.rs | head -1)
sed -n '240,290p' "$F"
echo '--- make check conditions ---'
grep -n 'make check\|MAKE_CHECK\|skip\|check' "$F" | head -10
