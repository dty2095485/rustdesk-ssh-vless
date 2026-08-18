#!/usr/bin/env bash
docker logs --since 240s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep 'Tcp connection' | grep -v '117.144' | tail -15
