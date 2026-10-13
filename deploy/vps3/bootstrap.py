#!/usr/bin/env python3
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

ROOT = Path('/opt/rustdesk-server')
IMAGE = 'rustdesk-server-combined:reality-20260929'
SNI = 'www.nvidia.com'
os.chdir(ROOT)
os.umask(0o077)

def run(args, capture=False):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None).stdout

for folder in ['data', 'x-ui-data', 'x-ui-acme', 'internal-tls']:
    (ROOT / folder).mkdir(exist_ok=True)
if (ROOT / 'client-settings.json').exists():
    raise RuntimeError('Existing deployment detected; refusing to replace credentials')
# The bundled supervisor expects hbvless to run. It stays loopback-only.
run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '3650', '-subj', '/CN=localhost', '-keyout', str(ROOT/'internal-tls/privkey.pem'), '-out', str(ROOT/'internal-tls/fullchain.pem')], True)
(ROOT/'.env').write_text('VLESS_UUID=' + str(uuid.uuid4()) + '\n')
credentials = {'address': '203.0.113.30', 'port': 443, 'sni': SNI, 'uuid': str(uuid.uuid4()), 'short_id': secrets.token_hex(8), 'fingerprint': 'chrome', 'flow': 'xtls-rprx-vision', 'panel_username': 'rd_' + secrets.token_hex(4), 'panel_password': secrets.token_urlsafe(24), 'panel_path': '/' + secrets.token_hex(12) + '/'}
key_output = run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', '/app/bin/xray-linux-amd64', IMAGE, 'x25519'], True)
private = re.search(r'^PrivateKey:\s*(\S+)', key_output, re.M).group(1)
credentials['public_key'] = re.search(r'^(?:Password(?: \(PublicKey\))?|PublicKey):\s*(\S+)', key_output, re.M).group(1)
run(['docker', 'run', '--rm', '--network', 'none', '-v', str(ROOT/'x-ui-data')+':/etc/x-ui', '--entrypoint', '/app/x-ui', IMAGE, 'setting', '-username', credentials['panel_username'], '-password', credentials['panel_password'], '-webBasePath', credentials['panel_path'], '-listenIP', '127.0.0.1', '-port', '2053'], True)
run(['docker', 'compose', 'up', '-d'])
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))
base = 'http://127.0.0.1:2053' + credentials['panel_path']

def post(path, values):
    data = urllib.parse.urlencode(values).encode()
    csrf = json.loads(opener.open(base + 'csrf-token', timeout=10).read())
    token = csrf.get('token') or csrf.get('obj') or csrf.get('data')
    if isinstance(token, dict):
        token = token.get('token')
    if not isinstance(token, str):
        raise RuntimeError('Unexpected CSRF response fields: ' + str(list(csrf)))
    request = urllib.request.Request(base + path, data, headers={'Origin': 'http://127.0.0.1:2053', 'Referer': base, 'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-Token': token})
    try:
        result = json.loads(opener.open(request, timeout=10).read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(str(error) + ': ' + error.read().decode(errors='replace')[:300]) from error
    if not result.get('success'):
        raise RuntimeError('Panel API failed: ' + str(result.get('msg')))
    return result

for attempt in range(30):
    try:
        post('login', {'username': credentials['panel_username'], 'password': credentials['panel_password']})
        break
    except Exception:
        if attempt == 29:
            raise
        time.sleep(1)
settings = {'clients': [{'id': credentials['uuid'], 'email': 'rustdesk-client', 'flow': credentials['flow'], 'enable': True, 'limitIp': 0, 'totalGB': 0, 'expiryTime': 0, 'subId': secrets.token_hex(8), 'reset': 0}], 'decryption': 'none', 'fallbacks': []}
stream = {'network': 'tcp', 'security': 'reality', 'realitySettings': {'show': False, 'target': SNI+':443', 'xver': 0, 'serverNames': [SNI], 'privateKey': private, 'shortIds': [credentials['short_id']], 'settings': {'publicKey': credentials['public_key'], 'fingerprint': 'chrome', 'serverName': SNI, 'spiderX': '/'}}}
existing = json.loads(opener.open(base + 'panel/api/inbounds/list', timeout=10).read())
ours = next((item for item in existing.get('obj', []) if item.get('remark') == 'RustDesk REALITY 443'), None)
endpoint = 'panel/api/inbounds/update/' + str(ours['id']) if ours else 'panel/api/inbounds/add'
post(endpoint, {'remark': 'RustDesk REALITY 443', 'enable': 'true', 'listen': '0.0.0.0', 'port': 443, 'protocol': 'vless', 'settings': json.dumps(settings), 'streamSettings': json.dumps(stream), 'sniffing': json.dumps({'enabled': False}), 'allocate': json.dumps({'strategy': 'always', 'refresh': 5, 'concurrency': 3}), 'total': 0, 'expiryTime': 0})
default_template = json.loads(run(['docker', 'exec', 'rustdesk-server', 'cat', '/app/bin/config.json'], True))
default_template['inbounds'] = [item for item in default_template.get('inbounds', []) if item.get('tag') == 'api']
run(['docker', 'stop', 'rustdesk-server'])
with sqlite3.connect(ROOT/'x-ui-data/x-ui.db') as db:
    row = db.execute("SELECT value FROM settings WHERE key='xrayTemplateConfig'").fetchone()
    template = json.loads(row[0]) if row else default_template
    template.setdefault('outbounds', []).append({'tag': 'rustdesk-loopback', 'protocol': 'freedom', 'settings': {'finalRules': [{'action': 'allow', 'ip': ['127.0.0.1'], 'port': '22115-22117'}, {'action': 'block'}]}})
    rules = template.setdefault('routing', {}).setdefault('rules', [])
    position = 1 if rules and rules[0].get('inboundTag') == ['api'] else 0
    rules[position:position] = [{'type': 'field', 'user': ['rustdesk-client'], 'network': 'tcp', 'ip': ['127.0.0.1'], 'port': '22115-22117', 'outboundTag': 'rustdesk-loopback'}, {'type': 'field', 'user': ['rustdesk-client'], 'outboundTag': 'blocked'}]
    if row:
        db.execute("UPDATE settings SET value=? WHERE key='xrayTemplateConfig'", (json.dumps(template),))
    else:
        db.execute("INSERT INTO settings(key,value) VALUES('xrayTemplateConfig',?)", (json.dumps(template),))
    db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('subEnable','false')")
run(['docker', 'start', 'rustdesk-server'])
credentials['rustdesk_key'] = (ROOT/'data/id_ed25519.pub').read_text().strip()
(ROOT/'client-settings.json').write_text(json.dumps(credentials, indent=2) + '\n')
print('VPS3 initialized: REALITY 443, restricted RustDesk route, private Web UI, independent credentials')
