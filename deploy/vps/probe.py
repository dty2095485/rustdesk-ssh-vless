import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import uuid
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--server', help='Override transport host for isolated canary testing')
parser.add_argument('--port', type=int, default=443)
parser.add_argument('--skip-public-port-check', action='store_true')
args = parser.parse_args()

params = json.loads(Path(r'<workspace>\.ssh\vps3-client-settings.json').read_text())

def exact(stream, n):
    data = b''
    while len(data) < n:
        piece = stream.recv(n-len(data))
        if not piece:
            raise RuntimeError('peer closed')
        data += piece
    return data

def frame(data):
    size = len(data)
    count = next(i for i in range(1,5) if size < 1 << (8*i-2))
    return ((size << 2) | (count-1)).to_bytes(count, 'little') + data

def recv_frame(stream):
    first = exact(stream, 1)
    count = (first[0]&3)+1
    size = int.from_bytes(first+exact(stream,count-1),'little') >> 2
    return exact(stream,size)

with socket.socket() as sock:
    sock.bind(('127.0.0.1',0))
    local_port = sock.getsockname()[1]
config = {'log': {'loglevel':'warning'}, 'inbounds':[{'listen':'127.0.0.1','port':local_port,'protocol':'socks','settings':{'auth':'noauth'}}], 'outbounds':[{'protocol':'vless','settings':{'vnext':[{'address':args.server or params['address'],'port':args.port,'users':[{'id':params['uuid'],'flow':params['flow'],'encryption':'none'}]}]},'streamSettings':{'network':'raw','security':'reality','realitySettings':{'serverName':params['sni'],'fingerprint':params['fingerprint'],'password':params['public_key'],'shortId':params['short_id']}}}]}

def tunnel(port):
    sock = socket.create_connection(('127.0.0.1',local_port),timeout=8)
    sock.sendall(b'\x05\x01\x00')
    assert exact(sock,2) == b'\x05\x00'
    sock.sendall(b'\x05\x01\x00\x01\x7f\x00\x00\x01'+port.to_bytes(2,'big'))
    assert exact(sock,10)[1] == 0
    return sock

with tempfile.TemporaryDirectory(prefix='rd-vps3-probe-') as directory:
    path = Path(directory)/'config.json'
    path.write_text(json.dumps(config))
    process = subprocess.Popen([r'C:\Program Files\RustDesk\xray.exe','run','-c',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
    try:
        time.sleep(1)
        for port in [22115,22116]:
            with tunnel(port) as sock:
                sock.sendall(frame(bytes.fromhex('a20100')))
                assert recv_frame(sock).startswith(bytes.fromhex('aa01'))
                print('PASS REALITY -> RustDesk protocol', port)
        with tunnel(22117) as first, tunnel(22117) as second:
            pairing = str(uuid.uuid4()).encode()
            request = b'\x0a\x0bdeployment3\x12'+bytes([len(pairing)])+pairing
            payload = b'\x92\x01'+bytes([len(request)])+request
            first.sendall(frame(payload))
            time.sleep(0.2)
            second.sendall(frame(payload))
            time.sleep(0.3)
            sample = b'RustDesk-REALITY-VPS3-'*3000
            first.sendall(sample)
            assert exact(second,len(sample)) == sample
            second.sendall(sample)
            assert exact(first,len(sample)) == sample
            print('PASS REALITY -> hbbr bidirectional relay', len(sample), 'bytes each way')
        with tunnel(22) as denied:
            denied.settimeout(3)
            try:
                response = denied.recv(32)
            except TimeoutError:
                response = b''
            assert not response
            print('PASS RustDesk credential cannot proxy SSH 22')
    finally:
        process.terminate()
        process.wait(timeout=5)

for port in ([] if args.skip_public_port_check else [21115,21116,21117,21118,21119,2053,2222]):
    try:
        with socket.create_connection((params['address'],port),timeout=1) as sock:
            sock.sendall(frame(bytes.fromhex('a20100')))
            sock.settimeout(2)
            if sock.recv(32):
                raise RuntimeError(f'unexpected public backend protocol response {port}')
            print('PASS backend connection closed without response', port)
    except (TimeoutError,ConnectionRefusedError):
        print('PASS backend port not publicly reachable',port)
