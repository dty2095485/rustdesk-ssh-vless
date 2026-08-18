#!/usr/bin/env bash
docker logs --since 300s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -iE 'relay|punch|auth' | tail -12
