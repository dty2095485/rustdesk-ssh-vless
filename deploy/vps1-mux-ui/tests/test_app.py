"""Offline regression and security tests; never contacts or modifies a VPS."""
import copy
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / 'app.py'
SPEC = importlib.util.spec_from_file_location('mux_app', str(MODULE_PATH))
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


def initial_config():
    return {
        'default_target': '127.0.0.1:4443',
        'connect_timeout': '5s',
        'proxy_timeout': '24h',
        'rules': [
            {'id': 'nas-browser', 'name': 'NAS 浏览器', 'sni': 'nas.example.com',
             'alpn': ['h2', 'http/1.1'], 'target': '127.0.0.1:4443', 'enabled': True},
            {'id': 'nas-tls', 'name': 'NAS TLS', 'sni': 'nas.example.com',
             'alpn': [], 'target': '127.0.0.1:8443', 'enabled': True},
            {'id': 'rd-reality', 'name': 'RustDesk REALITY', 'sni': 'rd.example.com',
             'alpn': [], 'target': '127.0.0.1:10443', 'enabled': True},
            {'id': 'test', 'name': '测试', 'sni': 'test.example.com',
             'alpn': [], 'target': '127.0.0.1:12443', 'enabled': True},
        ],
    }


def regex_route(config, sni, alpn):
    """Exercise generated Nginx map regexes using their documented first-match order."""
    for line in app.render_config(app.normalize_config(config)).decode('utf-8').splitlines():
        value = line.strip()
        if value.startswith('~*'):
            pattern, target = value.split(None, 1)
            if re.search(pattern[2:], sni + ':' + alpn, re.IGNORECASE):
                return target.rstrip(';')
    return config['default_target']


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = initial_config()

    def test_existing_routes_preserved(self):
        examples = [
            ('nas.example.com', 'h2', 4443),
            ('nas.example.com', 'http/1.1', 4443),
            ('nas.example.com', 'h2,http/1.1', 4443),
            ('nas.example.com', 'custom,h2,other', 4443),
            ('NAS.EXAMPLE.COM', 'h2', 4443),
            ('nas.example.com', '', 8443),
            ('nas.example.com', 'custom', 8443),
            ('nas.example.com', 'h2c', 8443),
            ('nas.example.com', 'xh2', 8443),
            ('nas.example.com', 'http/1.10', 8443),
            ('rd.example.com', 'h2', 10443),
            ('test.example.com', '', 12443),
            ('example.com', 'h2', 4443),
            ('rd.example.com.evil.example', '', 4443),
            ('', '', 4443),
        ]
        for sni, alpn, port in examples:
            with self.subTest(sni=sni, alpn=alpn):
                self.assertEqual(regex_route(self.config, sni, alpn), '127.0.0.1:' + str(port))

    def test_rule_order_and_disabling(self):
        self.config['rules'][0]['enabled'] = False
        self.assertEqual(regex_route(self.config, 'nas.example.com', 'h2'), '127.0.0.1:8443')
        self.config['rules'][0]['enabled'] = True
        self.config['rules'].reverse()
        self.assertEqual(regex_route(self.config, 'nas.example.com', 'h2'), '127.0.0.1:8443')

    def test_wildcard_subdomain_boundaries(self):
        self.config['rules'] = [dict(self.config['rules'][2], sni='*.example.com')]
        for sni in ('rd.example.com', 'a.b.example.com'):
            self.assertEqual(regex_route(self.config, sni, ''), '127.0.0.1:10443')
        for sni in ('example.com', 'example.com.evil.example', 'notexample.com'):
            self.assertEqual(regex_route(self.config, sni, ''), '127.0.0.1:4443')

    def test_config_normalization(self):
        self.config['rules'][0]['sni'] = ' NAS.EXAMPLE.COM '
        self.config['rules'][0]['alpn'] = ['h2', 'h2', 'http/1.1']
        actual = app.normalize_config(self.config)
        self.assertEqual(actual['rules'][0]['sni'], 'nas.example.com')
        self.assertEqual(actual['rules'][0]['alpn'], ['h2', 'http/1.1'])
        self.assertEqual(self.config['rules'][0]['sni'], ' NAS.EXAMPLE.COM ')

    def test_target_allowlist(self):
        self.assertEqual(app.target_address('[::1]:8443'), ('::1', 8443))
        self.assertEqual(app.target_address('127.0.0.1:22'), ('127.0.0.1', 22))
        for target in ('0.0.0.0:8443', 'localhost:8443', '192.0.2.100:8443',
                       '127.0.0.2:8443', '127.0.0.1:0', '127.0.0.1:65536',
                       '127.0.0.1:443', '127.0.0.1:18080', '[::1]:443',
                       '127.0.0.1:8443;', '127.0.0.1:8443\ninclude /tmp/evil;', None):
            with self.subTest(target=target), self.assertRaises(app.Problem):
                app.target_address(target)
        with self.assertRaises(app.Problem):
            app.target_address('127.0.0.1:19080', manager_port=19080)

    def test_sni_and_alpn_injection_rejected(self):
        for sni in ('rd.example.com; include x;', 'rd.example.com\nserver{}', '$variable',
                    'rd.example.com"', 'rd.example.com:', 'a..example.com', '-a.example.com'):
            candidate = copy.deepcopy(self.config)
            candidate['rules'][0]['sni'] = sni
            with self.subTest(sni=sni), self.assertRaises(app.Problem):
                app.normalize_config(candidate)
        for alpn in (['h2;'], ['h2\n'], ['${variable}'], [''], [1], None, ['h2'] * 9):
            candidate = copy.deepcopy(self.config)
            candidate['rules'][0]['alpn'] = alpn
            with self.subTest(alpn=alpn), self.assertRaises(app.Problem):
                app.normalize_config(candidate)

    def test_limits_and_types(self):
        for key, value in [('connect_timeout', '61s'), ('connect_timeout', '0s'),
                           ('connect_timeout', '1s;'), ('proxy_timeout', '49h'),
                           ('proxy_timeout', 24), ('rules', None), ('rules', [{}] * 41)]:
            candidate = copy.deepcopy(self.config)
            candidate[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(app.Problem):
                app.normalize_config(candidate)
        for field, value in [('id', 'bad/id'), ('name', 'bad\nname'), ('enabled', 'true')]:
            candidate = copy.deepcopy(self.config)
            candidate['rules'][0][field] = value
            with self.subTest(field=field), self.assertRaises(app.Problem):
                app.normalize_config(candidate)
        duplicate = copy.deepcopy(self.config)
        duplicate['rules'][1]['id'] = duplicate['rules'][0]['id']
        with self.assertRaises(app.Problem):
            app.normalize_config(duplicate)


class FakeManager(app.Manager):
    def __init__(self, root, config_path):
        super().__init__(root, config_path, 'nonexistent-nginx', Path(root) / 'pid', 18080)
        self.command_calls = []
        self.reload_calls = 0
        self.fail_tests = set()
        self.fail_reloads = set()

    def command(self, *args):
        self.command_calls.append(args)
        if len(self.command_calls) in self.fail_tests:
            raise app.Problem('test failed', 422)
        return 'test successful'

    def reload_verified(self):
        self.reload_calls += 1
        if self.reload_calls in self.fail_reloads:
            raise app.Problem('reload failed', 503)

    def healthy(self):
        return True


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        salt = bytes.fromhex('00' * 16)
        self.settings = {'username': 'admin', 'salt': salt.hex(),
                         'password_hash': hashlib.pbkdf2_hmac('sha256', b'strong-password', salt, 250000).hex()}
        (self.root / 'settings.json').write_text(json.dumps(self.settings), encoding='utf-8')
        self.config_path = self.root / 'vless_mux.conf'
        self.original = b'# original formatting retained\n' + app.render_config(initial_config())
        self.config_path.write_bytes(self.original)
        self.state_path = self.root / 'state.json'
        self.state_path.write_bytes(app.json_bytes({'config': initial_config(), 'source_hash': app.digest(self.original)}))
        self.original_state = self.state_path.read_bytes()
        self.manager = FakeManager(self.root, self.config_path)

    def tearDown(self):
        self.temp.cleanup()

    def candidate(self):
        value = initial_config()
        value['rules'][2]['target'] = '127.0.0.1:11443'
        return value

    def test_apply_snapshot_and_restore_original_bytes(self):
        result = self.manager.apply(self.candidate(), app.digest(self.original))
        self.assertTrue(result['ok'])
        self.assertEqual(self.manager.reload_calls, 1)
        self.assertFalse(self.manager.read_state()['drift'])
        self.assertEqual(self.config_path.read_bytes(), app.render_config(self.candidate()))
        backup = json.loads((self.manager.backups_path / (result['backup_id'] + '.json')).read_text(encoding='utf-8'))
        self.assertEqual(backup['config'], initial_config())
        restored = self.manager.restore(result['backup_id'], result['revision'])
        self.assertTrue(restored['ok'])
        self.assertEqual(self.config_path.read_bytes(), self.original)
        self.assertEqual(json.loads(self.state_path.read_text(encoding='utf-8'))['config'], initial_config())

    def test_test_failure_restores_bytes_without_reload(self):
        self.manager.fail_tests = {1}
        with self.assertRaises(app.Problem) as error:
            self.manager.apply(self.candidate(), app.digest(self.original))
        self.assertEqual(error.exception.status, 422)
        self.assertEqual(self.config_path.read_bytes(), self.original)
        self.assertEqual(self.state_path.read_bytes(), self.original_state)
        self.assertEqual(self.manager.reload_calls, 0)
        self.assertEqual(len(self.manager.list_backups()), 1)

    def test_reload_failure_restores_and_reloads(self):
        self.manager.fail_reloads = {1}
        with self.assertRaises(app.Problem) as error:
            self.manager.apply(self.candidate(), app.digest(self.original))
        self.assertEqual(error.exception.status, 422)
        self.assertEqual(self.config_path.read_bytes(), self.original)
        self.assertEqual(self.state_path.read_bytes(), self.original_state)
        self.assertEqual(self.manager.reload_calls, 2)

    def test_rollback_failure_reports_critical_status(self):
        self.manager.fail_reloads = {1, 2}
        with self.assertRaises(app.Problem) as error:
            self.manager.apply(self.candidate(), app.digest(self.original))
        self.assertEqual(error.exception.status, 503)
        self.assertEqual(self.config_path.read_bytes(), self.original)
        self.assertEqual(self.state_path.read_bytes(), self.original_state)

    def test_state_write_failure_rolls_back_nginx(self):
        atomic = app.atomic_write

        def fail_state(path, data, mode=0o600):
            if Path(path) == self.state_path:
                raise OSError('disk full')
            return atomic(path, data, mode)

        with mock.patch.object(app, 'atomic_write', side_effect=fail_state):
            with self.assertRaises(app.Problem):
                self.manager.apply(self.candidate(), app.digest(self.original))
        self.assertEqual(self.config_path.read_bytes(), self.original)
        self.assertEqual(self.state_path.read_bytes(), self.original_state)
        self.assertEqual(self.manager.reload_calls, 2)

    def test_revision_and_external_drift_block_overwrite(self):
        with self.assertRaises(app.Problem) as error:
            self.manager.apply(self.candidate(), 'old-revision')
        self.assertEqual(error.exception.status, 409)
        outside = self.original + b'# changed by another editor\n'
        self.config_path.write_bytes(outside)
        self.assertTrue(self.manager.read_state()['drift'])
        with self.assertRaises(app.Problem) as error:
            self.manager.apply(self.candidate(), app.digest(outside))
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.config_path.read_bytes(), outside)
        self.assertFalse(self.manager.list_backups())

    def test_restore_id_path_traversal_rejected(self):
        for value in ('../settings', '/tmp/backup', '20261001-000000-12345678/..', None):
            with self.subTest(value=value), self.assertRaises(app.Problem):
                self.manager.restore(value, app.digest(self.original))

    def test_login_session_and_rate_limit(self):
        session = self.manager.login('admin', 'strong-password')
        self.assertEqual(len(self.manager.session(session)['csrf']), 43)
        for unused in range(5):
            with self.assertRaises(app.Problem) as error:
                self.manager.login('admin', 'wrong-password')
            self.assertEqual(error.exception.status, 401)
        with self.assertRaises(app.Problem) as error:
            self.manager.login('admin', 'strong-password')
        self.assertEqual(error.exception.status, 429)
        with mock.patch.object(app.time, 'time', return_value=self.manager.sessions[session]['time'] + app.SESSION_AGE + 1):
            with self.assertRaises(app.Problem) as error:
                self.manager.session(session)
            self.assertEqual(error.exception.status, 401)


class HTTPTests(ManagerTests):
    """End-to-end local HTTP checks, with all Nginx calls stubbed."""
    def setUp(self):
        super().setUp()
        self.server = app.Server(('127.0.0.1', 0), app.Handler)
        self.server.manager = self.manager
        self.port = self.server.server_address[1]
        self.origin = 'http://127.0.0.1:' + str(self.port)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        super().tearDown()

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        supplied = {'Host': '127.0.0.1:' + str(self.port), 'Origin': self.origin}
        supplied.update(headers or {})
        body = None if payload is None else json.dumps(payload).encode()
        if body is not None:
            supplied['Content-Type'] = 'application/json'
        connection.request(method, path, body=body, headers=supplied)
        response = connection.getresponse()
        result = (response.status, dict(response.getheaders()), json.loads(response.read()))
        connection.close()
        return result

    def login_headers(self):
        status, headers, unused = self.request('POST', '/api/login', {'username': 'admin', 'password': 'strong-password'})
        self.assertEqual(status, 200)
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        status, unused, state = self.request('GET', '/api/state', headers={'Cookie': cookie})
        self.assertEqual(status, 200)
        return {'Cookie': cookie, 'X-CSRF-Token': state['csrf_token']}, state

    def test_authentication_csrf_and_security_headers(self):
        status, unused, body = self.request('GET', '/api/state')
        self.assertEqual(status, 401)
        auth, state = self.login_headers()
        status, unused, body = self.request('POST', '/api/apply', {'config': self.candidate(), 'revision': state['revision']}, {'Cookie': auth['Cookie']})
        self.assertEqual(status, 403)
        status, headers, body = self.request('POST', '/api/preview', {'config': self.candidate(), 'revision': state['revision']}, auth)
        self.assertEqual(status, 200)
        self.assertIn('11443', body['nginx_config'])
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        status, unused, body = self.request('POST', '/api/logout', {}, auth)
        self.assertEqual(status, 200)
        status, unused, body = self.request('GET', '/api/state', headers=auth)
        self.assertEqual(status, 401)

    def test_foreign_host_origin_and_fetch_site_rejected(self):
        for headers in ({'Host': 'evil.example:18080'},
                        {'Origin': 'https://evil.example'},
                        {'Origin': ''},
                        {'Sec-Fetch-Site': 'cross-site'},
                        {'Host': '127.0.0.1:18080@evil.example'},
                        {'Host': '127.0.0.1:not-a-port'},
                        {'Host': '['}):
            with self.subTest(headers=headers):
                status, unused, body = self.request('POST', '/api/login', {'username': 'admin', 'password': 'strong-password'}, headers)
                self.assertEqual(status, 403)

    def test_unicode_username_fails_cleanly(self):
        status, unused, body = self.request('POST', '/api/login', {'username': '不存在的用户', 'password': 'wrong-password'})
        self.assertEqual(status, 401)

    def test_public_https_login_csrf_and_secure_cookie(self):
        self.manager.settings['public_origins'] = ['https://vps1.example.com']
        origin_headers = {'Host': 'vps1.example.com', 'Origin': 'https://vps1.example.com',
                          'X-Forwarded-Proto': 'https', 'Sec-Fetch-Site': 'same-origin'}
        status, headers, body = self.request('POST', '/api/login',
            {'username': 'admin', 'password': 'strong-password'}, origin_headers)
        self.assertEqual(status, 200)
        self.assertIn('; Secure', headers['Set-Cookie'])
        auth = dict(origin_headers, Cookie=headers['Set-Cookie'].split(';', 1)[0])
        status, unused, state = self.request('GET', '/api/state', headers=auth)
        self.assertEqual(status, 200)
        status, unused, body = self.request('POST', '/api/preview',
            {'config': state['config'], 'revision': state['revision']}, auth)
        self.assertEqual(status, 403)
        auth['X-CSRF-Token'] = state['csrf_token']
        status, unused, body = self.request('POST', '/api/preview',
            {'config': state['config'], 'revision': state['revision']}, auth)
        self.assertEqual(status, 200)
        for extra in ({'Origin': 'https://evil.example'}, {'Host': 'evil.example'},
                      {'X-Forwarded-Proto': 'http'}, {'X-Forwarded-Proto': ''},
                      {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(extra=extra):
                status, unused, body = self.request('POST', '/api/preview',
                    {'config': state['config'], 'revision': state['revision']}, dict(auth, **extra))
                self.assertEqual(status, 403)

    def test_public_host_not_enabled_by_forwarded_headers_alone(self):
        status, unused, body = self.request('POST', '/api/login',
            {'username': 'admin', 'password': 'strong-password'},
            {'Host': 'vps1.example.com', 'Origin': 'https://vps1.example.com', 'X-Forwarded-Proto': 'https'})
        self.assertEqual(status, 403)

    def test_public_uri_prefix_and_scoped_cookie(self):
        prefix = '/unit-test-private-path/'
        self.manager.settings.update({'public_origins': ['https://vps1.example.com'], 'public_path': prefix})
        headers = {'Host': 'vps1.example.com', 'Origin': 'https://vps1.example.com',
                   'X-Forwarded-Proto': 'https', 'X-Forwarded-Prefix': prefix}
        payload = {'username': 'admin', 'password': 'strong-password'}
        for extra in ({'X-Forwarded-Prefix': ''}, {'X-Forwarded-Prefix': '/wrong-path/'}):
            status, unused, body = self.request('POST', '/api/login', payload, dict(headers, **extra))
            self.assertEqual(status, 403)
        status, reply, body = self.request('POST', '/api/login', payload, headers)
        self.assertEqual(status, 200)
        self.assertIn('Path=' + prefix + ';', reply['Set-Cookie'])
        self.assertIn('; Secure', reply['Set-Cookie'])
        headers['Cookie'] = reply['Set-Cookie'].split(';', 1)[0]
        status, unused, state = self.request('GET', '/api/state', headers=headers)
        self.assertEqual(status, 200)
        headers['X-CSRF-Token'] = state['csrf_token']
        status, reply, unused = self.request('POST', '/api/logout', {}, headers)
        self.assertEqual(status, 200)
        self.assertIn('Path=' + prefix + ';', reply['Set-Cookie'])

    def test_bad_payload_and_large_body_rejected(self):
        status, unused, body = self.request('POST', '/api/login', ['not', 'an', 'object'])
        self.assertEqual(status, 400)
        status, unused, body = self.request('POST', '/api/login', {'username': 'admin', 'password': 'x' * (app.MAX_BODY + 1)})
        self.assertEqual(status, 413)

    def test_api_apply_and_loopback_probe_validation(self):
        auth, state = self.login_headers()
        status, unused, body = self.request('POST', '/api/probe', {'target': '8.8.8.8:443'}, auth)
        self.assertEqual(status, 400)
        status, unused, body = self.request('POST', '/api/apply', {'config': self.candidate(), 'revision': state['revision']}, auth)
        self.assertEqual(status, 200)
        self.assertTrue(body['ok'])
        status, unused, body = self.request('POST', '/api/apply', {'config': initial_config(), 'revision': state['revision']}, auth)
        self.assertEqual(status, 409)


if __name__ == '__main__':
    unittest.main(verbosity=2)
