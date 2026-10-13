#!/usr/bin/env python3
"""Deploy only vps1.example.com:443 -> HTTPS14443 -> HTTP18080, with rollback."""
import datetime
import hashlib
import http.cookiejar
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid

APP = Path('/opt/rustdesk-mux-ui/app.py')
CANDIDATE = Path('/opt/rustdesk-mux-ui/app-https-candidate.py')
ROOT = Path('/var/lib/rustdesk-mux-ui')
SITE = Path('/www/server/panel/vhost/nginx/vps1.example.com.conf')
STREAM = Path('/www/server/panel/vhost/nginx/tcp/vless_mux.conf')
NGINX = '/www/server/nginx/sbin/nginx'
PUBLIC = 'https://vps1.example.com'
BASE = 'http://127.0.0.1:18080'
MANIFEST = ROOT / 'https-domain.json'


def run(argv):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=25)
    if result.returncode:
        raise RuntimeError('command failed: ' + argv[0])
    return result


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(base, credentials):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(path, payload=None, token=None, origin=None):
        headers = {'Origin': origin or base, 'Content-Type': 'application/json', 'Sec-Fetch-Site': 'same-origin'}
        if token:
            headers['X-CSRF-Token'] = token
        request = urllib.request.Request(base + path, headers=headers,
            data=None if payload is None else json.dumps(payload).encode())
        with opener.open(request, timeout=15) as response:
            body = response.read()
            return response.status, body, dict(response.headers)
    call('/api/login', {'username': credentials['username'], 'password': credentials['password']})
    return call


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('site configuration differs; refusing ambiguous edit')
    return text.replace(old, new, 1)


def main():
    if os.geteuid() != 0:
        raise RuntimeError('root required')
    os.umask(0o077)
    if MANIFEST.exists() or MANIFEST.is_symlink():
        raise RuntimeError('HTTPS domain deployment already recorded; inspect before repeating')
    paths = [APP, ROOT/'settings.json', SITE, STREAM, ROOT/'state.json']
    if any(path.is_symlink() or not path.is_file() for path in paths + [CANDIDATE]):
        raise RuntimeError('unsafe/missing deployment target')
    if sha(APP.read_bytes()) != 'dd272ce20908ae3a88ac6cf7561b6a5c959813ffca780c8b784ae543a098bd64':
        raise RuntimeError('management program differs from reviewed baseline')
    with socket.socket() as check:
        check.bind(('127.0.0.1', 14443))
    spec = importlib.util.spec_from_file_location('mux_original', str(APP))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    run(['/usr/bin/python3', '-m', 'py_compile', str(CANDIDATE)])
    credentials = json.loads((ROOT/'connection-settings.json').read_text())
    local = api(BASE, credentials)
    before_state = json.loads(local('/api/state')[1])
    if before_state['drift'] or not before_state['service']['healthy']:
        raise RuntimeError('mux drift/unhealthy; no files changed')
    new_config = json.loads(json.dumps(before_state['config']))
    old_vps = [rule for rule in new_config['rules'] if rule['sni'] == 'vps1.example.com']
    rule = {'id': old_vps[0]['id'] if old_vps else 'vps1-management', 'name': 'VPS1 443 分流管理 HTTPS',
            'sni': 'vps1.example.com', 'alpn': [], 'target': '127.0.0.1:14443', 'enabled': True}
    new_config['rules'] = [rule] + [item for item in new_config['rules'] if item['sni'] != 'vps1.example.com']
    original_site = SITE.read_text()
    updated_site = replace_one(original_site, 'listen 443 ssl;', 'listen 127.0.0.1:14443 ssl;')
    updated_site = replace_one(updated_site, 'if ($server_port != 443)', 'if ($scheme = http)')
    updated_site = replace_one(updated_site, 'proxy_set_header Host 127.0.0.1;', 'proxy_set_header Host $host;')
    updated_site = replace_one(updated_site, 'proxy_set_header X-Forwarded-Port $server_port;', 'proxy_set_header X-Forwarded-Port 443;')
    settings = json.loads((ROOT/'settings.json').read_text())
    allowed = settings.get('public_origins', [])
    if not isinstance(allowed, list):
        raise RuntimeError('invalid pre-existing public origins setting')
    settings['public_origins'] = list(dict.fromkeys(allowed + [PUBLIC]))
    directory = ROOT / ('https-backup-' + datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700)
    original = {str(path): path.read_bytes() for path in paths}
    entries = {}
    for index, path in enumerate(paths):
        backup = directory / (str(index) + '-' + path.name)
        helper.atomic_write(backup, original[str(path)])
        entries[str(path)] = {'backup': str(backup), 'before_hash': sha(original[str(path)])}
    data = {'status': 'preparing', 'files': entries, 'directory': str(directory)}
    helper.atomic_write(MANIFEST, helper.json_bytes(data))
    switched = False
    restart_done = False
    try:
        if any(path.read_bytes() != original[str(path)] for path in paths):
            raise RuntimeError('configuration edited concurrently; refusing overwrite')
        helper.atomic_write(APP, CANDIDATE.read_bytes(), 0o755)
        helper.atomic_write(ROOT/'settings.json', helper.json_bytes(settings))
        helper.atomic_write(SITE, updated_site.encode(), 0o644)
        run([NGINX, '-t'])
        restart_done = True
        run(['systemctl', 'restart', 'rustdesk-mux-ui'])
        time.sleep(0.5)
        local = api(BASE, credentials)
        live = json.loads(local('/api/state')[1])
        if live['config'] != before_state['config'] or live['revision'] != before_state['revision']:
            raise RuntimeError('mux changed concurrently')
        local('/api/preview', {'config': new_config, 'revision': live['revision']}, live['csrf_token'])
        response = json.loads(local('/api/apply', {'config': new_config, 'revision': live['revision']}, live['csrf_token'])[1])
        switched = True
        data['mux_backup_id'] = response['backup_id']
        live = json.loads(local('/api/state')[1])
        if live['config'] != new_config or live['drift']:
            raise RuntimeError('mux apply did not preserve expected configuration')
        # CA validation is enabled; this must be the domain's real certificate.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(PUBLIC + '/', timeout=15) as response:
            html = response.read()
            if response.status != 200 or b'443' not in html:
                raise RuntimeError('public management page not available')
        public = api(PUBLIC, credentials)
        public_state = json.loads(public('/api/state')[1])
        payload = {'config': public_state['config'], 'revision': public_state['revision']}
        public('/api/preview', payload, public_state['csrf_token'])
        # Save the identical configuration through HTTPS to verify the real
        # browser path can apply safely, not merely load a login page.
        public('/api/apply', payload, public_state['csrf_token'])
        public_state = json.loads(public('/api/state')[1])
        if public_state['config'] != new_config or public_state['drift']:
            raise RuntimeError('public API save changed unrelated rules')
        for token, origin in [('', PUBLIC), (public_state['csrf_token'], 'https://evil.example')]:
            try:
                public('/api/preview', {'config': new_config, 'revision': public_state['revision']}, token, origin)
            except urllib.error.HTTPError as error:
                if error.code != 403:
                    raise
            else:
                raise RuntimeError('public CSRF/origin protection failed')
        public('/api/logout', {}, public_state['csrf_token'])
        data['status'] = 'deployed'
        data['config'] = new_config
        for path in paths:
            entries[str(path)]['after_hash'] = sha(path.read_bytes())
        helper.atomic_write(MANIFEST, helper.json_bytes(data))
        print('PASS HTTPS domain/certificate, login, state, preview, identical save, CSRF/origin rejection, logout.')
        print('Applied vps1.example.com:443 -> 127.0.0.1:14443 HTTPS -> 127.0.0.1:18080 HTTP.')
        print('Existing other rules preserved; backup: ' + str(directory))
    except Exception:
        # Preserve a concurrent management edit rather than blindly overwrite.
        live_state = json.loads((ROOT/'state.json').read_text())
        if live_state['config'] not in (new_config, before_state['config']):
            raise RuntimeError('deployment failed and mux was edited concurrently; protected backup retained for manual rollback')
        for path in paths:
            helper.atomic_write(path, original[str(path)], 0o755 if path == APP else 0o644 if path in (SITE,STREAM) else 0o600)
        run([NGINX, '-t'])
        run([NGINX, '-s', 'reload'])
        if restart_done:
            run(['systemctl', 'restart', 'rustdesk-mux-ui'])
        data['status'] = 'rolled-back'
        helper.atomic_write(MANIFEST, helper.json_bytes(data))
        raise


if __name__ == '__main__':
    main()
