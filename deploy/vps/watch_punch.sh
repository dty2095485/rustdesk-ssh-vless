#!/usr/bin/env bash
# Watch for punch/relay traffic from iOS during a connect attempt.
timeout 120 docker logs -f --since 1s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -iE 'punch|relay|register|Data' | head -30
