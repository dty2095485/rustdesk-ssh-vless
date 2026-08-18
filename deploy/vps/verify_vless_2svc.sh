#!/usr/bin/env bash
echo '== synthetic VLESS handshake: 443 -> nginx SNI nas -> hbvless(gw) -> hbbs 127.0.0.1:21116 =='
( printf '\x00\x50\x59\x74\x46\x7f\xef\x46\xae\xae\x4e\x29\x0f\x80\xf7\x7d\x06\x00\x01\x52\x7c\x01\x7f\x00\x00\x01'; sleep 3 ) \
  | timeout 8 openssl s_client -quiet -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | xxd | head -3
echo '== synthetic VLESS relay handshake: port 443 -> hbvless -> hbbr 127.0.0.1:21117 =='
( printf '\x00\x50\x59\x74\x46\x7f\xef\x46\xae\xae\x4e\x29\x0f\x80\xf7\x7d\x06\x00\x01\x01\xbb\x01\x7f\x00\x00\x01'; sleep 3 ) \
  | timeout 8 openssl s_client -quiet -connect 127.0.0.1:443 -servername nas.your-domain.example 2>/dev/null | xxd | head -3
