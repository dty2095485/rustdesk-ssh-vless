"""Run manager API regression tests locally on VPS1."""
import http.cookiejar
import json
from pathlib import Path
import urllib.error
import urllib.request

base = 'http://127.0.0.1:18080'
credentials = json.loads(Path('/var/lib/rustdesk-mux-ui/connection-settings.json').read_text(encoding='utf-8'))
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def call(path, payload=None, token=None):
    headers = {'Origin': base, 'Content-Type': 'application/json'}
    if token is not None:
        headers['X-CSRF-Token'] = token
    req = urllib.request.Request(base + path, None if payload is None else json.dumps(payload).encode(), headers=headers)
    try:
        response = opener.open(req, timeout=30)
        return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())

assert call('/api/state')[0] == 401
assert call('/api/login', {'username': credentials['username'], 'password': credentials['password']})[0] == 200
status, state = call('/api/state')
assert status == 200 and not state['drift'] and state['service']['healthy']
token = state['csrf_token']
assert len(state['config']['rules']) == 4
assert call('/api/preview', {'config': state['config'], 'revision': state['revision']}, 'bad-token')[0] == 403
assert call('/api/apply', {'config': state['config'], 'revision': 'stale'}, token)[0] == 409
invalid = json.loads(json.dumps(state['config']))
invalid['rules'][0]['target'] = '127.0.0.1:443'
assert call('/api/apply', {'config': invalid, 'revision': state['revision']}, token)[0] == 400
assert call('/api/state')[1]['revision'] == state['revision']
for rule in state['config']['rules']:
    assert call('/api/probe', {'target': rule['target']}, token)[1]['reachable']
assert call('/api/preview', {'config': state['config'], 'revision': state['revision']}, token)[0] == 200
status, result = call('/api/apply', {'config': state['config'], 'revision': state['revision']}, token)
assert status == 200, result
backup = result['backup_id']
applied = call('/api/state')[1]
assert applied['config'] == state['config'] and applied['service']['healthy'] and not applied['drift']
# Restore the original bytes to leave production behavior exactly unchanged.
status, result = call('/api/restore', {'id': backup, 'revision': applied['revision']}, token)
assert status == 200, result
restored = call('/api/state')[1]
assert restored['revision'] == state['revision'] and restored['service']['healthy'] and not restored['drift']
assert call('/api/logout', {}, token)[0] == 200
assert call('/api/state')[0] == 401
print('PASS: login, CSRF, revision conflict, target validation, backend probes, preview, live apply/reload, backup restore, logout')
print('Production mux original bytes restored; four existing rules unchanged')
