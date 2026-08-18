#!/bin/sh
set -eu

/usr/bin/healthcheck-combined.sh
/package/admin/s6/command/s6-svstat /run/s6-rc/servicedirs/hbssh | grep -q '^up'
netstat -lnt | awk '$4 ~ /:22$/ && $6 == "LISTEN" { found = 1 } END { exit found ? 0 : 1 }'
