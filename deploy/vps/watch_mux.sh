#!/usr/bin/env bash
tail -30 /www/wwwlogs/tcp-access.log | grep -E '18:31:4[0-9]|18:32:0' || tail -20 /www/wwwlogs/tcp-access.log
