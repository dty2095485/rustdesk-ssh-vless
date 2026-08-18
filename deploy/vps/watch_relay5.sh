#!/usr/bin/env bash
timeout 180 docker logs -f --since 1s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -iE 'relay' | head -20
