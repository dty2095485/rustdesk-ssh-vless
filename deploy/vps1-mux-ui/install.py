"""Install the loopback manager without rewriting Nginx production rules."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess

os.umask(0o077)
code = Path('/opt/rustdesk-mux-ui')
root = Path('/var/lib/rustdesk-mux-ui')
config = Path('/www/server/panel/vhost/nginx/tcp/vless_mux.conf')
root.mkdir(mode=0o700, exist_ok=True)
settings_path = root / 'settings.json'
credentials_path = root / 'connection-settings.json'
if not settings_path.exists():
    password = secrets.token_urlsafe(24)
    salt = secrets.token_hex(16)
    username = 'REPLACE_WITH_USERNAME'
    settings_path.write_text(json.dumps({'username': username, 'salt': salt, 'password_hash': hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 250000).hex()}, indent=2) + '\n', encoding='utf-8')
    credentials_path.write_text(json.dumps({'address': '203.0.113.10', 'ssh_port': 22, 'manager_port': 18080, 'local_port': 12080, 'url': 'http://127.0.0.1:12080/', 'username': username, 'password': password}, indent=2) + '\n', encoding='utf-8')
state_path = root / 'state.json'
if not state_path.exists():
    live = config.read_bytes()
    expected = ['~^nas\\.example\\.com:.*(h2|http/1\\.1) 127.0.0.1:4443;', '~^nas\\.example\\.com:', '~^rd\\.example\\.com:', '~^test\\.example\\.com:', 'default                               127.0.0.1:4443;', 'proxy_connect_timeout 5s;', 'proxy_timeout 24h;']
    text = live.decode('utf-8')
    if not all(part in text for part in expected):
        raise RuntimeError('Production rules changed; refusing automatic initial import')
    initial = {'rules': [
        {'id': 'nas-web', 'name': 'NAS 浏览器访问', 'sni': 'nas.example.com', 'alpn': ['h2', 'http/1.1'], 'target': '127.0.0.1:4443', 'enabled': True},
        {'id': 'nas-vless', 'name': 'NAS VLESS TCP+TLS', 'sni': 'nas.example.com', 'alpn': [], 'target': '127.0.0.1:8443', 'enabled': True},
        {'id': 'rd-reality', 'name': 'RustDesk REALITY', 'sni': 'rd.example.com', 'alpn': [], 'target': '127.0.0.1:10443', 'enabled': True},
        {'id': 'test-web', 'name': '现有测试站点', 'sni': 'test.example.com', 'alpn': [], 'target': '127.0.0.1:12443', 'enabled': True},
    ], 'default_target': '127.0.0.1:4443', 'connect_timeout': '5s', 'proxy_timeout': '24h'}
    state_path.write_text(json.dumps({'config': initial, 'source_hash': hashlib.sha256(live).hexdigest()}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (root / 'original-vless_mux.conf').write_bytes(live)
for path in root.glob('*'):
    if path.is_file():
        path.chmod(0o600)
subprocess.run(['nginx', '-t'], check=True)
unit = Path('/etc/systemd/system/rustdesk-mux-ui.service')
unit.write_bytes((code / 'rustdesk-mux-ui.service').read_bytes())
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'enable', 'rustdesk-mux-ui'], check=True)
subprocess.run(['systemctl', 'restart', 'rustdesk-mux-ui'], check=True)
print('Installed: loopback 127.0.0.1:18080; production mux file was not modified')
