#!/usr/bin/env bash
timeout 240 docker logs -f --since 1s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -E 'VLESS-DBG|Punch hole|relay request|paired' | head -40
echo WATCH_END
