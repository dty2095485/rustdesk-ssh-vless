#!/usr/bin/env python3
"""Add an unguessable URI prefix to the existing HTTPS management vhost."""
import datetime
import hashlib
import http.cookiejar
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path('/var/lib/rustdesk-mux-ui')
APP = Path('/opt/rustdesk-mux-ui/app.py')
INDEX = Path('/opt/rustdesk-mux-ui/static/index.html')
SITE = Path('/www/server/panel/vhost/nginx/vps1.example.com.conf')
SETTINGS = ROOT/'settings.json'
CONNECTION = ROOT/'connection-settings.json'
MANIFEST = ROOT/'uri-domain.json'
PUBLIC = 'https://vps1.example.com'
NGINX = '/www/server/nginx/sbin/nginx'


def run(argv):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=25)
    if result.returncode:
        raise RuntimeError('command failed: ' + argv[0])
    return result


def sha(data):
    return hashlib.sha256(data).hexdigest()


def client(base):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    parsed = urllib.parse.urlsplit(base)
    origin = parsed.scheme + '://' + parsed.netloc
    def call(path, payload=None, token=None, supplied_origin=None):
        headers = {'Origin': supplied_origin or origin, 'Content-Type': 'application/json', 'Sec-Fetch-Site': 'same-origin'}
        if token:
            headers['X-CSRF-Token'] = token
        request = urllib.request.Request(base.rstrip('/') + path, headers=headers,
            data=None if payload is None else json.dumps(payload).encode())
        with opener.open(request, timeout=15) as response:
            return response.status, response.read(), dict(response.headers)
    return call


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('site differs from reviewed configuration')
    return text.replace(old, new, 1)


def expect_denied(call, path, payload=None, token=None, origin=None, code=404):
    try:
        call(path, payload, token, origin)
    except urllib.error.HTTPError as error:
        if error.code == code:
            return
        raise
    raise RuntimeError('expected blocked endpoint remained accessible')


def main():
    if os.geteuid() != 0:
        raise RuntimeError('root required')
    os.umask(0o077)
    if MANIFEST.exists() or MANIFEST.is_symlink():
        raise RuntimeError('URI deployment already recorded; inspect before repeating')
    targets = [APP, INDEX, SITE, SETTINGS, CONNECTION]
    candidate_app = APP.with_name('app-uri-candidate.py')
    candidate_index = APP.parent/'index-uri-candidate.html'
    if any(path.is_symlink() or not path.is_file() for path in targets + [candidate_app,candidate_index]):
        raise RuntimeError('missing/unsafe deployment file')
    if sha(APP.read_bytes()) != '9169322ce4aa214d494893462abde6d902cd954865fac6effcdf413856a02760':
        raise RuntimeError('management program changed since review')
    if sha(INDEX.read_bytes()) != '171537f0981409bd2299f7af933844955000572fe3be7a9355e79e09e07aabc1':
        raise RuntimeError('management UI changed since review')
    run(['/usr/bin/python3', '-m', 'py_compile', str(candidate_app)])
    spec = importlib.util.spec_from_file_location('mux_original', str(APP))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    credentials = json.loads(CONNECTION.read_text())
    local = client('http://127.0.0.1:18080')
    login = {'username': credentials['username'], 'password': credentials['password']}
    local('/api/login', login)
    original_state = json.loads(local('/api/state')[1])
    if original_state['drift'] or not original_state['service']['healthy']:
        raise RuntimeError('mux drift/unhealthy; no change made')
    # 192 random bits; the path is additional defense, not an authentication replacement.
    prefix = '/m-' + secrets.token_urlsafe(24) + '/'
    original = {str(path): path.read_bytes() for path in targets}
    text = SITE.read_text()
    text = replace_one(text, 'location ^~ / {', 'location ^~ ' + prefix + ' {')
    text = replace_one(text, 'proxy_pass http://127.0.0.1:18080;', 'proxy_pass http://127.0.0.1:18080/;')
    text = replace_one(text, 'proxy_set_header X-Forwarded-Proto $scheme;',
        'proxy_set_header X-Forwarded-Proto $scheme;\n        proxy_set_header X-Forwarded-Prefix ' + prefix + ';')
    text = replace_one(text, '    #PROXY-CONF-END',
        '    location = ' + prefix.rstrip('/') + ' { return 308 ' + prefix + '; }\n'
        '    location ^~ / { return 404; }\n    #PROXY-CONF-END')
    settings = json.loads(SETTINGS.read_text())
    if PUBLIC not in settings.get('public_origins', []):
        raise RuntimeError('HTTPS domain is not enabled')
    settings['public_path'] = prefix
    directory = ROOT/('uri-backup-' + datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(4))
    directory.mkdir(mode=0o700)
    files = {}
    for index, path in enumerate(targets):
        backup = directory/(str(index)+'-'+path.name)
        helper.atomic_write(backup, original[str(path)])
        files[str(path)] = {'backup': str(backup), 'before_hash': sha(original[str(path)])}
    manifest = {'status': 'preparing', 'files': files, 'directory': str(directory)}
    helper.atomic_write(MANIFEST, helper.json_bytes(manifest))
    restarting = False
    try:
        if any(path.read_bytes() != original[str(path)] for path in targets):
            raise RuntimeError('target edited concurrently')
        helper.atomic_write(APP, candidate_app.read_bytes(), 0o755)
        helper.atomic_write(INDEX, candidate_index.read_bytes(), 0o644)
        helper.atomic_write(SITE, text.encode(), 0o644)
        helper.atomic_write(SETTINGS, helper.json_bytes(settings))
        run([NGINX, '-t'])
        restarting = True
        run(['systemctl', 'restart', 'rustdesk-mux-ui'])
        run([NGINX, '-s', 'reload'])
        time.sleep(0.8)
        public = client(PUBLIC + prefix)
        status, page, unused_headers = public('/')
        if status != 200 or b'const apiBase = window.location.pathname' not in page:
            raise RuntimeError('prefixed UI does not use relative API base')
        status, body, headers = public('/api/login', login)
        if 'Path=' + prefix + ';' not in headers.get('Set-Cookie','') or '; Secure' not in headers['Set-Cookie']:
            raise RuntimeError('HTTPS login cookie not scoped to private path')
        live = json.loads(public('/api/state')[1])
        if live['config'] != original_state['config'] or live['drift']:
            raise RuntimeError('unrelated stream rules changed')
        payload = {'config': live['config'], 'revision': live['revision']}
        public('/api/preview', payload, live['csrf_token'])
        public('/api/apply', payload, live['csrf_token'])
        live = json.loads(public('/api/state')[1])
        if live['config'] != original_state['config'] or live['drift']:
            raise RuntimeError('same-config save changed stream rules')
        expect_denied(public, '/api/preview', {'config': live['config'], 'revision': live['revision']}, code=403)
        expect_denied(public, '/api/preview', {'config': live['config'], 'revision': live['revision']}, live['csrf_token'], 'https://evil.example', 403)
        public('/api/logout', {}, live['csrf_token'])
        expect_denied(public, '/api/state', code=401)
        root_client = client(PUBLIC)
        for path in ['/', '/api/state', '/api/backups', '/not-the-management-path/']:
            expect_denied(root_client, path)
        expect_denied(root_client, '/api/login', login)
        # The original authenticated SSH tunnel still works without knowing the URI.
        local = client('http://127.0.0.1:18080')
        local('/api/login', login)
        state = json.loads(local('/api/state')[1])
        if state['config'] != original_state['config']:
            raise RuntimeError('SSH tunnel management state changed')
        local('/api/logout', {}, state['csrf_token'])
        connection = dict(credentials, public_url=PUBLIC+prefix, uri_path=prefix)
        helper.atomic_write(CONNECTION, helper.json_bytes(connection))
        manifest.update({'status': 'deployed', 'public_url': PUBLIC+prefix, 'uri_path': prefix})
        for path in targets:
            files[str(path)]['after_hash'] = sha(path.read_bytes())
        helper.atomic_write(MANIFEST, helper.json_bytes(manifest))
        print('PASS hidden URI UI/login/state/preview/save/logout, scoped Secure cookie, CSRF, origin, root/old-API 404, SSH tunnel.')
        print(json.dumps({'public_url': PUBLIC+prefix, 'uri_path': prefix, 'backup': str(directory)}))
    except Exception:
        for path in targets:
            helper.atomic_write(path, original[str(path)], 0o755 if path == APP else 0o644 if path in (INDEX,SITE) else 0o600)
        run([NGINX, '-t'])
        run([NGINX, '-s', 'reload'])
        if restarting:
            run(['systemctl', 'restart', 'rustdesk-mux-ui'])
        manifest['status'] = 'rolled-back'
        helper.atomic_write(MANIFEST, helper.json_bytes(manifest))
        raise


if __name__ == '__main__':
    main()
