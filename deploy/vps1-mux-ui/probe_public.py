"""Verify existing website and VLESS TLS through VPS1 public 443."""
import json
from pathlib import Path
import socket
import ssl
import uuid

profile = json.loads(Path(r'<workspace>\releases\windows\ssh\VPS1-network.json').read_text(encoding='utf-8'))
params = profile['vless']['tls_profile']

def exact(sock, size):
    data = b''
    while len(data) < size:
        part = sock.recv(size-len(data))
        if not part:
            raise RuntimeError('Peer closed before protocol reply')
        data += part
    return data

for sni in ['example.com', 'nas.example.com', 'rd.example.com']:
    context = ssl.create_default_context()
    context.set_alpn_protocols(['http/1.1'])
    with socket.create_connection(('203.0.113.10', 443), timeout=12) as raw:
        with context.wrap_socket(raw, server_hostname=sni) as tls:
            tls.sendall(('GET / HTTP/1.1\r\nHost: ' + sni + '\r\nConnection: close\r\n\r\n').encode())
            response = tls.recv(2048)
            assert response.startswith(b'HTTP/1.1 '), response[:100]
            print('PASS public website/fallback:', sni, response.split(b'\r\n')[0].decode())

# No HTTP ALPN: preserve the existing NAS VLESS TLS route to hbvless.
with socket.create_connection(('203.0.113.10', 443), timeout=12) as raw:
    with ssl.create_default_context().wrap_socket(raw, server_hostname=params['server_name']) as tls:
        header = b'\x00' + uuid.UUID(params['uuid']).bytes + b'\x00\x01' + (21116).to_bytes(2, 'big') + b'\x01\x7f\x00\x00\x01'
        tls.sendall(header + bytes.fromhex('0ca20100'))
        response = exact(tls, 2)
        assert response[0] == 0
        exact(tls, response[1])
        first = exact(tls, 1)
        count = (first[0] & 3) + 1
        size = int.from_bytes(first + exact(tls, count-1), 'little') >> 2
        assert exact(tls, size).startswith(bytes.fromhex('aa01'))
        print('PASS public VLESS TLS -> authenticated RustDesk registration protocol')
