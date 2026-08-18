#!/usr/bin/env bash
# Correct framing: 1-byte header = len<<2 for len<=63.
{
  printf '\x00\x50\x59\x74\x46\x7f\xef\x46\xae\xae\x4e\x29\x0f\x80\xf7\x7d\x06'   # ver + uuid
  printf '\x00'                                                                  # addons
  printf '\x01'                                                                  # cmd TCP
  printf '\x52\x7c'                                                              # port 21117
  printf '\x02\x0a'                                                              # domain, len 10
  printf 'your-domain.example'
  printf '\x34'                                                                  # frame header: 13<<2
  printf '\x92\x0b\x12\x09'                                                      # union18 len11 / field2 len9
  printf 'test-1234'
} | timeout 8 openssl s_client -quiet -connect 127.0.0.1:8443 -servername nas.your-domain.example 2>/dev/null | head -c 100 | xxd | head -3
echo '--- hbbr log check ---'
sleep 2
docker logs --since 20s rustdesk_rrsc-rustdesk_rrsC-1 2>&1 | grep -i 'relay request' | tail -3
