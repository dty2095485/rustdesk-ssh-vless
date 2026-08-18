#!/usr/bin/env bash
sleep 50
docker logs --tail 600 rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -E 'tcp loop|Tcp connection' | tail -20
