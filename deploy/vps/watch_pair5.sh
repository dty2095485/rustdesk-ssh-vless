#!/usr/bin/env bash
timeout 300 docker logs -f --since 1s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -iE 'relay request|paired|auth|Punch' | head -25
echo WATCH_END
