#!/usr/bin/env bash
sleep 55
docker logs --tail 800 rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -E 'tcp loop|Tcp connection' | tail -24
