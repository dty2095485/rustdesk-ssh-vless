#!/usr/bin/env bash
grep '02:51:5\|02:52:' /www/wwwlogs/tcp-access.log | tail -8
