#!/usr/bin/env bash
echo '--- who holds 8443 ---'
ss -ltnp | grep 8443 || echo '(none)'
echo '--- docker containers ---'
docker ps -a --format '{{.Names}} | {{.Status}}' | grep -iE 'rustdesk|hbvless'
echo '--- stray docker-proxy? ---'
ps aux | grep docker-proxy | grep -v grep | head -5
