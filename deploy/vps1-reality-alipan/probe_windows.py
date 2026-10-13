"""Test the installed Windows REALITY core against VPS1's public 443."""
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'vps1-tls-fallback'))
from probe import exact,frame,recv_frame,protobuf_text,protobuf_varint


def main():
    p=json.loads((ROOT/'client-parameters-private.json').read_text())
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
    config={'log':{'loglevel':'warning'},'inbounds':[{'listen':'127.0.0.1','port':port,'protocol':'socks','settings':{'auth':'noauth','udp':False}}],
            'outbounds':[{'protocol':'vless','settings':{'vnext':[{'address':p['server'],'port':int(p['port']),'users':[{'id':p['uuid'],'encryption':'none','flow':p['flow']}]}]},
                          'streamSettings':{'network':'raw','security':'reality','realitySettings':{'serverName':p['server_name'],'password':p['public_key'],'shortId':p['short_id'],'fingerprint':p['fingerprint']}}}]}
    def connect(destination):
        sock=socket.create_connection(('127.0.0.1',port),12);sock.settimeout(12)
        sock.sendall(b'\x05\x01\x00')
        if exact(sock,2)!=b'\x05\x00':raise RuntimeError('SOCKS handshake failed')
        sock.sendall(b'\x05\x01\x00\x01\x7f\x00\x00\x01'+struct.pack('!H',destination))
        head=exact(sock,4)
        if head[1]!=0:raise RuntimeError('SOCKS destination failed')
        size={1:4,4:16}.get(head[3])
        if head[3]==3:size=exact(sock,1)[0]
        exact(sock,size+2);return sock
    with tempfile.TemporaryDirectory(prefix='rd-alipan-probe-') as directory:
        path=Path(directory)/'config.json';path.write_text(json.dumps(config))
        with open(Path(directory)/'core.log','wb') as log:
            process=subprocess.Popen([r'C:\Program Files\RustDesk\xray.exe','run','-c',str(path)],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                for unused in range(50):
                    if process.poll() is not None:raise RuntimeError('Installed Xray failed to start')
                    try:
                        with socket.create_connection(('127.0.0.1',port),0.2):break
                    except OSError:time.sleep(0.1)
                for target in (22115,22116):
                    with connect(target) as sock:
                        sock.sendall(frame(bytes.fromhex('a20100')))
                        if not recv_frame(sock).startswith(bytes.fromhex('aa01')):raise RuntimeError('registration response mismatch')
                pairing=str(uuid.uuid4())
                body=protobuf_text(1,'windows-alipan-probe')+protobuf_text(2,pairing)
                message=frame(protobuf_varint((18<<3)|2)+protobuf_varint(len(body))+body)
                with connect(22117) as first:
                    first.sendall(message);time.sleep(0.2)
                    with connect(22117) as second:
                        second.sendall(message);time.sleep(0.3)
                        sample=b'Windows-REALITY-Alipan-test-'*3000
                        first.sendall(sample)
                        if exact(second,len(sample))!=sample:raise RuntimeError('relay forward mismatch')
                        second.sendall(sample)
                        if exact(first,len(sample))!=sample:raise RuntimeError('relay backward mismatch')
                print(json.dumps({'pass':True,'installed_windows_core':True,'public_port':443,'sni':p['server_name'],'registration_ports':[22115,22116],'relay_bytes_each_way':len(sample)}))
            finally:
                process.terminate();process.wait(timeout=10)


if __name__=='__main__':main()
