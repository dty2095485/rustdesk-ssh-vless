#!/usr/bin/env bash
export PATH=/home/dty/.cargo/bin:/home/dty/zig:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
cd /home/dty/build
DATABASE_URL=sqlite:/home/dty/build/db_v2.sqlite3 cargo check --bin hbbs > ~/build/ck.log 2>&1
RC=$?
tail -30 ~/build/ck.log
echo "cargo-rc=$RC"
