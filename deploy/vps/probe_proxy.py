"""Verify the proxy user through public REALITY and export its share link."""
import json
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.parse
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--server')
parser.add_argument('--port', type=int, default=443)
parser.add_argument('--no-export', action='store_true')
args = parser.parse_args()

root = Path(__file__).parent
p = json.loads((root / 'VPS3-proxy-settings.json').read_text())

def exact(sock, size):
    data = b''
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise RuntimeError('Connection closed')
        data += part
    return data

with socket.socket() as reserved:
    reserved.bind(('127.0.0.1', 0))
    port = reserved.getsockname()[1]
config = {'log': {'loglevel': 'warning'}, 'inbounds': [{'listen': '127.0.0.1', 'port': port, 'protocol': 'socks', 'settings': {'auth': 'noauth'}}], 'outbounds': [{'protocol': 'vless', 'settings': {'vnext': [{'address': args.server or p['address'], 'port': args.port, 'users': [{'id': p['uuid'], 'flow': p['flow'], 'encryption': 'none'}]}]}, 'streamSettings': {'network': 'raw', 'security': 'reality', 'realitySettings': {'serverName': p['sni'], 'fingerprint': p['fingerprint'], 'password': p['public_key'], 'shortId': p['short_id']}}}]}

def connect(host, target_port):
    sock = socket.create_connection(('127.0.0.1', port), timeout=12)
    sock.sendall(b'\x05\x01\x00')
    assert exact(sock, 2) == b'\x05\x00'
    domain = host.encode()
    sock.sendall(b'\x05\x01\x00\x03' + bytes([len(domain)]) + domain + target_port.to_bytes(2, 'big'))
    assert exact(sock, 10)[1] == 0
    return sock

with tempfile.TemporaryDirectory(prefix='vps3-proxy-test-') as directory:
    path = Path(directory) / 'config.json'
    path.write_text(json.dumps(config))
    process = subprocess.Popen([r'C:\Program Files\RustDesk\xray.exe', 'run', '-c', str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    try:
        time.sleep(1)
        with connect('example.com', 443) as raw:
            with ssl.create_default_context().wrap_socket(raw, server_hostname='example.com') as tls:
                tls.sendall(b'GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n')
                response = tls.recv(4096)
                assert b'200 OK' in response.split(b'\r\n', 1)[0], response[:80]
                print('PASS: proxy UUID -> Internet HTTPS, trusted certificate, HTTP 200')
        with connect('127.0.0.1', 22116) as denied:
            denied.sendall(bytes.fromhex('0ca20100'))
            denied.settimeout(4)
            try:
                reply = denied.recv(64)
            except TimeoutError:
                reply = b''
            assert not reply, 'Proxy user unexpectedly reached RustDesk backend'
            print('PASS: proxy UUID cannot reach private RustDesk backend')
    finally:
        process.terminate()
        process.wait(timeout=5)
query = urllib.parse.urlencode({'encryption': 'none', 'security': 'reality', 'sni': p['sni'], 'fp': p['fingerprint'], 'pbk': p['public_key'], 'sid': p['short_id'], 'type': 'tcp', 'flow': p['flow']})
link = 'vless://' + p['uuid'] + '@' + p['address'] + ':443?' + query + '#VPS3-Internet-REALITY'
if not args.no_export:
    (root / 'VPS3-proxy-link.txt').write_text(link + '\n', encoding='utf-8')
    print('Exported: VPS3-proxy-link.txt (separate from RustDesk JSON)')
