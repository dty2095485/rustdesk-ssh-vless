"""Exercise all existing REALITY UUID routes without modifying panel settings."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

os.umask(0o077)
sys.path.insert(0, '/opt/rustdesk-tls-fallback')
import migrate_reality_alipan as m

candidate = '--candidate' in sys.argv
container = 'rustdesk-panel39-canary' if candidate else 'rustdesk-server'
folder = Path('/opt/rustdesk-build/panel39/routes-' + str(time.time_ns() if hasattr(time, 'time_ns') else int(time.time() * 1000000)))
folder.mkdir(mode=0o700)
core = folder / 'xray'
subprocess.check_call(['docker', 'cp', container + ':/app/bin/xray-linux-amd64', str(core)])
core.chmod(0o700)
def start_core(directory, name, config, ports):
    path = directory / (name + '.json')
    m.save(path, config)
    subprocess.check_call([str(core), 'run', '-test', '-c', str(path)])
    with (directory / (name + '.log')).open('wb') as output:
        process = subprocess.Popen([str(core), 'run', '-c', str(path)], stdout=output, stderr=output)
    try:
        for port in ports:
            m.wait_port(port, True)
        return process
    except Exception:
        process.terminate()
        process.wait(timeout=10)
        raise
def stop_core(process):
    process.terminate()
    process.wait(timeout=10)
m.start_core = start_core
m.stop_core = stop_core
runtime = json.loads(subprocess.check_output(['docker', 'exec', container, 'cat', '/app/bin/config.json']))
inbound = next(i for i in runtime['inbounds'] if i.get('port') == 19443)
params = json.loads(Path('/var/lib/rustdesk-reality-alipan/client-parameters-private.json').read_text())
host, port = ('172.17.0.2', 19443) if candidate else ('203.0.113.10', 443)
clients = inbound['settings']['clients']
ins, outs = [], []
for index, client in enumerate(clients):
    tag = 'probe-' + str(index)
    ins.append({'tag': tag, 'listen': '127.0.0.1', 'port': 10890 + index, 'protocol': 'socks', 'settings': {'auth': 'noauth'}})
    outs.append({'tag': tag, 'protocol': 'vless', 'settings': {'vnext': [{'address': host, 'port': port,
        'users': [{'id': client['id'], 'encryption': 'none', 'flow': client.get('flow', '')}]}]},
        'streamSettings': {'network': 'raw', 'security': 'reality', 'realitySettings': {
        'fingerprint': 'chrome', 'serverName': m.SNI, 'password': params['public_key'],
        'shortId': params['short_id'], 'spiderX': '/'}}})
config = {'log': {'loglevel': 'warning'}, 'inbounds': ins, 'outbounds': outs,
          'routing': {'rules': [{'type': 'field', 'inboundTag': [o['tag']], 'outboundTag': o['tag']} for o in outs]}}
process = start_core(folder, 'clients', config, [10890 + i for i in range(len(clients))])
try:
    for index, client in enumerate(clients):
        local_port = 10890 + index
        if client['email'].startswith('rustdesk'):
            for target in (22115, 22116):
                with m.socks(local_port, '127.0.0.1', target) as stream:
                    stream.sendall(m.frame(bytes.fromhex('a20100')))
                    assert m.recv_frame(stream).startswith(bytes.fromhex('aa01'))
            payload = m.text_field(1, 'official-core-probe') + m.text_field(2, str(uuid.uuid4()))
            request = m.frame(m.varint((18 << 3) | 2) + m.varint(len(payload)) + payload)
            with m.socks(local_port, '127.0.0.1', 22117) as first:
                first.sendall(request)
                time.sleep(0.15)
                with m.socks(local_port, '127.0.0.1', 22117) as second:
                    second.sendall(request)
                    time.sleep(0.2)
                    sample = b'official-core-relay' * 3000
                    first.sendall(sample)
                    assert m.exact(second, len(sample)) == sample
                    second.sendall(sample)
                    assert m.exact(first, len(sample)) == sample
            try:
                with m.socks(local_port, '127.0.0.1', 22) as denied:
                    denied.settimeout(3)
                    assert not denied.recv(32), 'RustDesk user reached SSH'
            except (TimeoutError, ConnectionResetError):
                pass
            except RuntimeError as error:
                if str(error) not in ('SOCKS destination rejected', 'connection ended before response'):
                    raise
            print('PASS REALITY RustDesk registration/relay/restricted destination')
        else:
            # CentOS Python 3.6/OpenSSL may not negotiate the target site's TLS.
            # Use the new official image's curl with certificate validation.
            code = subprocess.check_output(['docker', 'run', '--rm', '--network', 'host',
                '--entrypoint', 'curl', 'rustdesk-server-combined:official-3.9.0-candidate',
                '-sS', '--max-time', '25', '--socks5-hostname', '127.0.0.1:' + str(local_port),
                '-o', '/dev/null', '-w', '%{http_code}', 'https://www.alipan.com/']).decode()
            assert 200 <= int(code) < 400, 'Proxy returned HTTP ' + code
            print('PASS proxy user', index + 1, 'configured Internet route, trusted HTTPS, HTTP', code)
finally:
    stop_core(process)
print('PASS all', len(clients), 'REALITY clients')
