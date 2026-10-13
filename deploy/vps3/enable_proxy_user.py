"""Add an Internet-only user without changing the RustDesk REALITY identity."""
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

root = Path('/opt/rustdesk-server')
os.umask(0o077)
params = json.loads((root / 'client-settings.json').read_text())
database = root / 'x-ui-data/x-ui.db'
backup = root / ('x-ui-data/x-ui-before-proxy-' + time.strftime('%Y%m%d-%H%M%S') + '.db')
with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
    source.backup(target)
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))
base = 'http://127.0.0.1:2053' + params['panel_path']

def post(path, fields):
    csrf = json.loads(opener.open(base + 'csrf-token', timeout=10).read())
    token = csrf.get('token') or csrf.get('obj') or csrf.get('data')
    if isinstance(token, dict):
        token = token.get('token')
    request = urllib.request.Request(base + path, urllib.parse.urlencode(fields).encode(), headers={'Origin': 'http://127.0.0.1:2053', 'Referer': base, 'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-Token': token})
    result = json.loads(opener.open(request, timeout=15).read())
    if not result.get('success'):
        raise RuntimeError('Panel request failed: ' + str(result.get('msg')))
    return result

def docker(*args):
    return subprocess.check_output(['docker', *args], text=True)

try:
    post('login', {'username': params['panel_username'], 'password': params['panel_password']})
    inbounds = json.loads(opener.open(base + 'panel/api/inbounds/list', timeout=10).read())['obj']
    inbound = next(item for item in inbounds if item['port'] == 443)
    settings = inbound['settings']
    if isinstance(settings, str):
        settings = json.loads(settings)
    assert any(c['id'] == params['uuid'] and c['email'] == 'rustdesk-client' for c in settings['clients'])
    proxy = next((c for c in settings['clients'] if c['email'] == 'proxy-internet'), None)
    if proxy is None:
        proxy = {'id': str(uuid.uuid4()), 'email': 'proxy-internet', 'flow': params['flow'], 'enable': True, 'limitIp': 0, 'totalGB': 0, 'expiryTime': 0, 'subId': secrets.token_hex(8), 'reset': 0}
        settings['clients'].append(proxy)
    docker('stop', 'rustdesk-server')
    with sqlite3.connect(database) as db:
        db.execute('UPDATE inbounds SET settings=? WHERE id=?', (json.dumps(settings), inbound['id']))
        now_ms = int(time.time() * 1000)
        client_row = db.execute('SELECT id FROM clients WHERE email=?', (proxy['email'],)).fetchone()
        if client_row is None:
            cursor = db.execute("INSERT INTO clients (email,sub_id,uuid,flow,security,limit_ip,total_gb,expiry_time,enable,tg_id,group_name,comment,reset,created_at,updated_at) VALUES (?,?,?,?,'auto',0,0,0,1,0,'','Internet proxy only',0,?,?)", (proxy['email'], proxy['subId'], proxy['id'], proxy['flow'], now_ms, now_ms))
            client_id = cursor.lastrowid
        else:
            client_id = client_row[0]
        db.execute('INSERT OR IGNORE INTO client_inbounds (client_id,inbound_id,flow_override,created_at) VALUES (?,?,?,?)', (client_id, inbound['id'], proxy['flow'], now_ms))
        db.execute('INSERT OR IGNORE INTO client_traffics (inbound_id,enable,email,up,down,expiry_time,total,reset,last_online,last_sub_fetch) VALUES (?,1,?,0,0,0,0,0,0,0)', (inbound['id'], proxy['email']))
        template = json.loads(db.execute("SELECT value FROM settings WHERE key='xrayTemplateConfig'").fetchone()[0])
        rules = template['routing']['rules']
        # Keep API and RustDesk rules first, and preserve private-network blocking.
        rules[:] = [r for r in rules if 'proxy-internet' not in r.get('user', [])]
        rules.append({'type': 'field', 'user': ['proxy-internet'], 'outboundTag': 'direct'})
        direct = next(o for o in template['outbounds'] if o['tag'] == 'direct')
        assert any(r.get('action') == 'block' and 'geoip:private' in r.get('ip', []) for r in direct['settings']['finalRules'])
        db.execute("UPDATE settings SET value=? WHERE key='xrayTemplateConfig'", (json.dumps(template),))
    docker('start', 'rustdesk-server')
    for attempt in range(30):
        try:
            running = json.loads(docker('exec', 'rustdesk-server', 'cat', '/app/bin/config.json'))
            active = next(i for i in running['inbounds'] if i.get('port') == 443)
            assert any(c['id'] == proxy['id'] for c in active['settings']['clients'])
            assert any(r.get('user') == ['proxy-internet'] for r in running['routing']['rules'])
            result = docker('exec', 'rustdesk-server', '/app/bin/xray-linux-amd64', 'run', '-test', '-c', '/app/bin/config.json')
            assert 'Configuration OK' in result
            break
        except Exception:
            if attempt == 29:
                raise
            time.sleep(1)
    profile = {k: params[k] for k in ['address', 'port', 'sni', 'public_key', 'short_id', 'fingerprint', 'flow']}
    profile['uuid'] = proxy['id']
    profile['purpose'] = 'Internet proxy only; private networks blocked'
    (root / 'proxy-settings.json').write_text(json.dumps(profile, indent=2) + '\n')
    print('PASS: existing REALITY 443 now has independent RustDesk and Internet users')
    print('Rollback database:', backup)
except Exception:
    docker('stop', 'rustdesk-server')
    with sqlite3.connect(backup) as source, sqlite3.connect(database) as target:
        source.backup(target)
    docker('start', 'rustdesk-server')
    print('FAILED: database restored; original RustDesk service restarted')
    raise
