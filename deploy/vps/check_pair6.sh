#!/usr/bin/env bash
docker logs --since 600s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -iE 'relay request|paired|Punch hole' | tail -20
