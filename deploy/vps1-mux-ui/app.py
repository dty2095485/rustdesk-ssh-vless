#!/usr/bin/env python3
"""Loopback-only UI for one allowlisted Nginx stream configuration."""
import argparse
import base64
import copy
import hashlib
import hmac
from http import cookies
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
from socketserver import ThreadingMixIn
import subprocess
import threading
import time
import urllib.parse

MAX_BODY = 65536
SESSION_AGE = 3600


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data, mode=0o600):
    path = Path(path)
    temporary = path.with_name('.' + path.name + '-' + secrets.token_hex(8))
    try:
        fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def target_address(value, manager_port=18080):
    if not isinstance(value, str):
        raise Problem('目标地址必须是字符串')
    match = re.fullmatch(r'(127\.0\.0\.1|\[::1\]):([0-9]{1,5})', value)
    if not match:
        raise Problem('目标仅允许 127.0.0.1:端口 或 [::1]:端口')
    port = int(match.group(2))
    if not 1 <= port <= 65535 or port in (443, manager_port):
        raise Problem('目标端口无效，不能指向公网 443 或管理页自身')
    return match.group(1).strip('[]'), port


def valid_timeout(value, maximum):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,5}[smh]', value):
        raise Problem('超时格式必须类似 5s、30m、24h')
    seconds = int(value[:-1]) * {'s': 1, 'm': 60, 'h': 3600}[value[-1]]
    if seconds > maximum:
        raise Problem('连接超时最多 60 秒，传输超时最多 48 小时')
    return value


def normalize_config(raw, manager_port=18080):
    if not isinstance(raw, dict):
        raise Problem('配置必须是对象')
    result = {'default_target': raw.get('default_target'), 'connect_timeout': valid_timeout(raw.get('connect_timeout'), 60), 'proxy_timeout': valid_timeout(raw.get('proxy_timeout'), 172800), 'rules': []}
    target_address(result['default_target'], manager_port)
    rules = raw.get('rules')
    if not isinstance(rules, list) or len(rules) > 40:
        raise Problem('规则列表最多 40 条')
    ids = set()
    for row in rules:
        if not isinstance(row, dict):
            raise Problem('规则格式错误')
        identity = row.get('id')
        if not isinstance(identity, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', identity) or identity in ids:
            raise Problem('规则 ID 无效或重复')
        ids.add(identity)
        name = row.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
            raise Problem('规则名称必须是 1–80 字符，不能含控制字符')
        sni = row.get('sni')
        if not isinstance(sni, str):
            raise Problem('SNI 格式错误')
        sni = sni.strip().lower()
        domain = sni[2:] if sni.startswith('*.') else sni
        if sni != '*' and (len(domain) > 253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', domain)):
            raise Problem('SNI 必须是域名、*.域名，或 *')
        alpn = row.get('alpn')
        if not isinstance(alpn, list) or len(alpn) > 8 or any(not isinstance(v, str) or not re.fullmatch(r'[a-z0-9][a-z0-9./_-]{0,23}', v) for v in alpn):
            raise Problem('ALPN 最多 8 个协议，例如 h2、http/1.1')
        if not isinstance(row.get('enabled'), bool):
            raise Problem('规则启停状态格式错误')
        target_address(row.get('target'), manager_port)
        result['rules'].append({'id': identity, 'name': name.strip(), 'sni': sni, 'alpn': list(dict.fromkeys(alpn)), 'target': row['target'], 'enabled': row['enabled']})
    return result


def render_config(config):
    lines = ['# Managed by rustdesk-mux-ui; use the Web UI to edit.', 'map "$ssl_preread_server_name:$ssl_preread_alpn_protocols" $rd_sni {']
    for rule in config['rules']:
        if not rule['enabled']:
            continue
        if rule['sni'] == '*':
            domain = '[^:]*'
        elif rule['sni'].startswith('*.'):
            domain = '(?:[^.:]+\\.)+' + re.escape(rule['sni'][2:])
        else:
            domain = re.escape(rule['sni'])
        protocol = ''
        if rule['alpn']:
            protocol = '(?:[^,]+,)*(?:' + '|'.join(re.escape(v) for v in rule['alpn']) + ')(?:,|$)'
        lines.append('    ~*^' + domain + ':' + protocol + ' ' + rule['target'] + ';')
    lines.extend(['    default ' + config['default_target'] + ';', '}', '', 'server {', '    listen 443;', '    proxy_pass $rd_sni;', '    ssl_preread on;', '    proxy_connect_timeout ' + config['connect_timeout'] + ';', '    proxy_timeout ' + config['proxy_timeout'] + ';', '}', ''])
    return '\n'.join(lines).encode('utf-8')


class Manager:
    def __init__(self, root, config_path, nginx, pid_path, port):
        self.root = Path(root)
        self.config_path = Path(config_path)
        self.nginx = nginx
        self.pid_path = Path(pid_path)
        self.port = port
        self.lock = threading.RLock()
        self.sessions = {}
        self.failures = []
        self.settings = json.loads((self.root / 'settings.json').read_text(encoding='utf-8'))
        self.state_path = self.root / 'state.json'
        self.backups_path = self.root / 'backups'
        self.backups_path.mkdir(mode=0o700, exist_ok=True)

    def read_state(self):
        with self.lock:
            state = json.loads(self.state_path.read_text(encoding='utf-8'))
            current = self.config_path.read_bytes()
            return {'revision': digest(current), 'config': state['config'], 'drift': digest(current) != state['source_hash'], 'service': {'name': 'nginx', 'healthy': self.healthy(), 'manager_port': self.port}, 'backup_count': len(self.list_backups())}

    def healthy(self):
        try:
            with socket.create_connection(('127.0.0.1', 443), timeout=1):
                return True
        except OSError:
            return False

    def children(self):
        master = int(self.pid_path.read_text(encoding='utf-8').strip())
        return set(Path('/proc/{}/task/{}/children'.format(master, master)).read_text(encoding='utf-8').split())

    def command(self, *args):
        result = subprocess.run([self.nginx, *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=15)
        if result.returncode != 0:
            raise Problem('Nginx 检查/重载失败：' + result.stdout[-3000:], 422)
        return result.stdout

    def reload_verified(self):
        before = self.children()
        self.command('-s', 'reload')
        for unused in range(30):
            if self.children() - before and self.healthy():
                return
            time.sleep(0.2)
        raise Problem('未确认 Nginx 新工作进程启动，配置将回滚', 503)

    def list_backups(self):
        return [{'id': p.stem, 'time': json.loads(p.read_text(encoding='utf-8'))['time']} for p in sorted(self.backups_path.glob('*.json'), reverse=True)]

    def snapshot(self, original, state):
        identity = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(4)
        atomic_write(self.backups_path / (identity + '.json'), json_bytes({'time': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()), 'config': state['config'], 'nginx': base64.b64encode(original).decode('ascii')}))
        return identity

    def apply(self, raw, revision, restored_bytes=None):
        config = normalize_config(raw, self.port)
        with self.lock:
            original = self.config_path.read_bytes()
            state = json.loads(self.state_path.read_text(encoding='utf-8'))
            if revision != digest(original):
                raise Problem('规则已被其他操作修改，请刷新页面后重试', 409)
            if state['source_hash'] != digest(original):
                raise Problem('检测到外部修改；已阻止覆盖，请先核对配置文件', 409)
            backup_id = self.snapshot(original, state)
            candidate = restored_bytes if restored_bytes is not None else render_config(config)
            reloaded = False
            try:
                atomic_write(self.config_path, candidate)
                self.command('-t')
                reloaded = True
                self.reload_verified()
                atomic_write(self.state_path, json_bytes({'config': config, 'source_hash': digest(candidate)}))
            except Exception as error:
                atomic_write(self.config_path, original)
                try:
                    self.command('-t')
                    if reloaded:
                        self.reload_verified()
                except Exception as rollback_error:
                    raise Problem('保存失败，回滚重载也失败，请立即检查 Nginx：' + str(rollback_error), 503)
                raise Problem('未应用修改，已恢复原配置：' + str(error), 422)
            for old in sorted(self.backups_path.glob('*.json'), reverse=True)[20:]:
                try:
                    old.unlink()
                except OSError:
                    print('Backup retention cleanup failed:', old.name, flush=True)
            return {'ok': True, 'revision': digest(candidate), 'backup_id': backup_id, 'message': '已检查并平滑重载，原配置已备份'}

    def restore(self, identity, revision):
        if not isinstance(identity, str) or not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[a-f0-9]{8}', identity):
            raise Problem('备份 ID 无效')
        path = self.backups_path / (identity + '.json')
        if not path.is_file():
            raise Problem('备份不存在', 404)
        backup = json.loads(path.read_text(encoding='utf-8'))
        return self.apply(backup['config'], revision, base64.b64decode(backup['nginx'], validate=True))

    def login(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str) or len(password) > 256:
            raise Problem('登录信息无效', 401)
        with self.lock:
            now = time.time()
            self.failures = [stamp for stamp in self.failures if now - stamp < 60]
            if len(self.failures) >= 5:
                raise Problem('登录失败次数过多，请一分钟后重试', 429)
            actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(self.settings['salt']), 250000).hex()
            if not (hmac.compare_digest(username.encode('utf-8'), self.settings['username'].encode('utf-8')) and hmac.compare_digest(actual, self.settings['password_hash'])):
                self.failures.append(now)
                raise Problem('用户名或密码错误', 401)
            self.sessions = {key: item for key, item in self.sessions.items() if now - item['time'] < SESSION_AGE}
            session = secrets.token_urlsafe(32)
            self.sessions[session] = {'time': now, 'csrf': secrets.token_urlsafe(32)}
            return session

    def session(self, key):
        with self.lock:
            session = self.sessions.get(key)
            if not session or time.time() - session['time'] >= SESSION_AGE:
                raise Problem('请先登录', 401)
            return session


class Handler(BaseHTTPRequestHandler):
    server_version = 'MuxUI'

    @property
    def manager(self):
        return self.server.manager

    def log_message(self, message, *args):
        return

    def authority(self):
        host = self.headers.get('Host', '')
        if len(self.headers.get_all('Host', [])) != 1 or len(self.headers.get_all('Origin', [])) > 1:
            raise Problem('重复的请求来源标识', 403)
        try:
            parsed = urllib.parse.urlsplit('http://' + host)
        except ValueError:
            raise Problem('无效的管理页 Host', 403)
        if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise Problem('无效的管理页 Host', 403)
        try:
            port = parsed.port
            if port is not None and not 1 <= port <= 65535:
                raise Problem('无效的管理页端口', 403)
        except ValueError:
            raise Problem('无效的管理页端口', 403)
        if parsed.hostname in ('127.0.0.1', 'localhost'):
            if port is None:
                raise Problem('无效的管理页端口', 403)
            expected_origin = 'http://' + host
            self.secure_origin = False
            self.cookie_path = '/'
        else:
            expected_origin = 'https://' + host
            allowed = self.manager.settings.get('public_origins', [])
            if (expected_origin not in allowed or self.client_address[0] != '127.0.0.1'
                    or self.headers.get('X-Forwarded-Proto') != 'https'):
                raise Problem('无效的管理页 HTTPS 来源', 403)
            self.secure_origin = True
            prefix = self.manager.settings.get('public_path', '/')
            if prefix != '/':
                if (not isinstance(prefix, str) or not re.fullmatch(r'/[A-Za-z0-9_-]{12,80}/', prefix)
                        or self.headers.get('X-Forwarded-Prefix') != prefix):
                    raise Problem('无效的管理页入口路径', 403)
            self.cookie_path = prefix
        origin = self.headers.get('Origin')
        if origin and origin != expected_origin:
            raise Problem('跨站请求已被拒绝', 403)
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise Problem('跨站请求已被拒绝', 403)

    def session_key(self):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
        except cookies.CookieError:
            raise Problem('登录 Cookie 无效', 401)
        return jar['mux_session'].value if 'mux_session' in jar else ''

    def send(self, status, data, content_type='application/json; charset=utf-8', cookie=None):
        body = data if isinstance(data, bytes) else json_bytes(data)
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            if getattr(self, 'secure_origin', False):
                cookie += '; Secure'
                cookie = cookie.replace('; Path=/;', '; Path={};'.format(self.cookie_path))
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            self.authority()
            if self.path == '/':
                self.send(200, (Path(__file__).parent / 'static/index.html').read_bytes(), 'text/html; charset=utf-8')
                return
            session = self.manager.session(self.session_key())
            if self.path == '/api/state':
                state = self.manager.read_state()
                state['csrf_token'] = session['csrf']
                self.send(200, state)
            elif self.path == '/api/backups':
                with self.manager.lock:
                    self.send(200, {'backups': self.manager.list_backups()})
            else:
                raise Problem('页面不存在', 404)
        except Problem as error:
            self.send(error.status, {'ok': False, 'message': str(error)})
        except Exception:
            self.send(500, {'ok': False, 'message': '读取失败，请检查管理服务日志'})

    def do_POST(self):
        try:
            self.authority()
            if not self.headers.get('Origin'):
                raise Problem('缺少同源请求标识', 403)
            if self.headers.get('Transfer-Encoding'):
                raise Problem('不支持分块请求')
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                raise Problem('请求长度无效')
            if not 0 < length <= MAX_BODY:
                raise Problem('请求内容过大或为空', 413)
            self.connection.settimeout(10)
            try:
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
            except (ValueError, UnicodeError):
                raise Problem('JSON 格式错误')
            if not isinstance(payload, dict):
                raise Problem('请求必须是对象')
            if self.path == '/api/login':
                key = self.manager.login(payload.get('username'), payload.get('password'))
                self.send(200, {'ok': True}, cookie='mux_session={}; HttpOnly; SameSite=Strict; Path=/; Max-Age={}'.format(key, SESSION_AGE))
                return
            key = self.session_key()
            session = self.manager.session(key)
            token = self.headers.get('X-CSRF-Token', '')
            if not hmac.compare_digest(token, session['csrf']):
                raise Problem('安全令牌无效，请刷新页面', 403)
            if self.path == '/api/logout':
                with self.manager.lock:
                    self.manager.sessions.pop(key, None)
                self.send(200, {'ok': True}, cookie='mux_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            elif self.path == '/api/preview':
                config = normalize_config(payload.get('config'), self.manager.port)
                if payload.get('revision') != self.manager.read_state()['revision']:
                    raise Problem('配置已变化，请刷新', 409)
                self.send(200, {'ok': True, 'nginx_config': render_config(config).decode(), 'message': '预览仅校验表单；应用时执行完整 nginx -t'})
            elif self.path == '/api/apply':
                self.send(200, self.manager.apply(payload.get('config'), payload.get('revision')))
            elif self.path == '/api/restore':
                self.send(200, self.manager.restore(payload.get('id'), payload.get('revision')))
            elif self.path == '/api/probe':
                address = target_address(payload.get('target'), self.manager.port)
                try:
                    with socket.create_connection(address, timeout=2):
                        reachable = True
                except OSError:
                    reachable = False
                self.send(200, {'ok': True, 'reachable': reachable, 'message': '端口可连接（不代表协议认证成功）' if reachable else '目标端口当前不可连接'})
            else:
                raise Problem('接口不存在', 404)
        except Problem as error:
            self.send(error.status, {'ok': False, 'message': str(error)})
        except Exception as error:
            print('Request failed:', type(error).__name__, flush=True)
            self.send(500, {'ok': False, 'message': '操作失败，请检查管理服务日志'})


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        return connection, address


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/var/lib/rustdesk-mux-ui')
    parser.add_argument('--config', default='/www/server/panel/vhost/nginx/tcp/vless_mux.conf')
    parser.add_argument('--nginx', default='/usr/bin/nginx')
    parser.add_argument('--pid', default='/www/server/nginx/logs/nginx.pid')
    parser.add_argument('--port', type=int, default=18080)
    args = parser.parse_args()
    os.umask(0o077)
    manager = Manager(args.root, args.config, args.nginx, args.pid, args.port)
    server = Server(('127.0.0.1', args.port), Handler)
    server.manager = manager
    print('443 mux manager listening on 127.0.0.1:' + str(args.port), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
