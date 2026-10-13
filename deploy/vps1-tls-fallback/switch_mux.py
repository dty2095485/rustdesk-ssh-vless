"""Apply/restore the compatibility migration through the existing mux UI API."""
import argparse
import datetime
import fcntl
import http.cookiejar
import json
import os
from pathlib import Path
import socket
import urllib.request
import uuid

ROOT = Path('/var/lib/rustdesk-tls-fallback')
STATE = ROOT / 'mux-switch.json'
BASE = 'http://127.0.0.1:18080'


def save(value):
    temporary = STATE.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(STATE))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['apply', 'unify', 'rollback', 'status'])
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('run on VPS1 as root')
    os.umask(0o077)
    if ROOT.is_symlink() or STATE.is_symlink():
        raise RuntimeError('unsafe state path')
    ROOT.mkdir(mode=0o700, exist_ok=True)
    with (ROOT / '.mux-switch.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute(args.action)


def execute(action):
    credentials = json.loads(Path('/var/lib/rustdesk-mux-ui/connection-settings.json').read_text())
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(path, payload=None, token=None):
        headers = {'Origin': BASE, 'Content-Type': 'application/json'}
        if token:
            headers['X-CSRF-Token'] = token
        request = urllib.request.Request(BASE + path,
            None if payload is None else json.dumps(payload).encode('utf-8'), headers=headers)
        with opener.open(request, timeout=30) as response:
            return json.loads(response.read())

    call('/api/login', {'username': credentials['username'], 'password': credentials['password']})
    live = call('/api/state')
    if live['drift'] or not live['service']['healthy']:
        raise RuntimeError('mux drift/unhealthy; production not changed')
    if action == 'status':
        nas = [{k: rule[k] for k in ['name', 'alpn', 'target', 'enabled']}
               for rule in live['config']['rules'] if rule['sni'] == 'nas.example.com']
        print(json.dumps({'healthy': True, 'nas_rules': nas}, ensure_ascii=False, indent=2))
        return
    if action == 'rollback':
        saved = json.loads(STATE.read_text(encoding='utf-8'))
        if saved.get('status') not in ('applied', 'preparing'):
            raise RuntimeError('no completed switch to restore')
        if live['config'] != saved['new_config']:
            raise RuntimeError('mux edited since migration; preserving newer changes')
        restore(call, saved, live)
        restored = call('/api/state')
        if restored['config'] != saved['old_config'] or not restored['service']['healthy']:
            raise RuntimeError('restoration verification failed')
        saved['status'] = 'rolled-back'
        save(saved)
        print('Restored prior NAS mux rule through the management API.')
        return
    if STATE.exists() and action != 'unify':
        raise RuntimeError('switch manifest already exists; inspect/restore before repeating')
    with socket.create_connection(('127.0.0.1', 18444), timeout=2):
        pass
    updated = json.loads(json.dumps(live['config']))
    nas = [rule for rule in updated['rules'] if rule['sni'] == 'nas.example.com']
    if action == 'unify':
        if STATE.exists():
            archive = ROOT / ('mux-before-unify-' + datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S-')
                              + uuid.uuid4().hex[:8] + '.json')
            with archive.open('xb') as stream:
                stream.write(STATE.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
        unified = {'id': nas[0]['id'] if nas else 'nas-xray',
                   'name': 'NAS Xray TLS / 协议回落', 'sni': 'nas.example.com',
                   'alpn': [], 'target': '127.0.0.1:18444', 'enabled': True}
        updated['rules'] = [unified] + [rule for rule in updated['rules']
                                        if rule['sni'] != 'nas.example.com']
    else:
        if len(nas) != 2 or not all(rule['enabled'] for rule in nas):
            raise RuntimeError('unexpected NAS rules; production not changed')
        if set(nas[0]['alpn']) != {'h2', 'http/1.1'} or nas[0]['target'] != '127.0.0.1:4443':
            raise RuntimeError('NAS browser rule changed; production not changed')
        if nas[1]['alpn'] or nas[1]['target'] != '127.0.0.1:8443':
            raise RuntimeError('legacy NAS rule changed; production not changed')
        nas[0]['target'] = '127.0.0.1:18444'
        nas[0]['name'] = 'NAS Xray TLS / 网站回落'
        nas[1]['name'] = 'NAS 旧版 TLS 兼容'
    call('/api/preview', {'config': updated, 'revision': live['revision']}, live['csrf_token'])
    saved = {'status': 'preparing', 'mode': action, 'old_config': live['config'], 'new_config': updated}
    save(saved)
    try:
        result = call('/api/apply', {'config': updated, 'revision': live['revision']}, live['csrf_token'])
        saved['backup_id'] = result['backup_id']
        saved['status'] = 'applied'
        save(saved)
        verified = call('/api/state')
        if verified['config'] != updated or verified['drift'] or not verified['service']['healthy']:
            raise RuntimeError('switch verification failed')
    except Exception:
        latest = call('/api/state')
        if latest['config'] == updated:
            restore(call, saved, latest)
        elif latest['config'] != saved['old_config']:
            raise RuntimeError('mux changed concurrently; preserving those changes')
        saved['status'] = 'rolled-back'
        save(saved)
        raise
    if action == 'unify':
        print('Applied: ALL NAS TLS traffic -> Xray 18444; no ALPN gateway split remains.')
    else:
        print('Applied: NAS h2/http1.1 -> Xray 18444; legacy no-ALPN -> original hbvless 8443.')
    print('REALITY, default website and other rules were preserved.')


def restore(call, saved, live):
    if saved.get('backup_id'):
        call('/api/restore', {'id': saved['backup_id'], 'revision': live['revision']}, live['csrf_token'])
    else:
        # The apply may succeed even if its HTTP response is interrupted.
        call('/api/apply', {'config': saved['old_config'], 'revision': live['revision']}, live['csrf_token'])


if __name__ == '__main__':
    main()
