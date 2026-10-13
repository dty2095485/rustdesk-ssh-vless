"""Produce importable network profiles; never export device passwords or IDs."""
import json
import os
from pathlib import Path
import tomllib

folder = Path(r'<workspace>\.ssh')
config = tomllib.loads((Path(os.environ['APPDATA'])/'RustDesk/config/RustDesk2.toml').read_text(encoding='utf-8'))
options = config.get('options', {})
vless = config.get('vless', {})
ssh = config.get('ssh', {})
network_keys = ['disable-udp', 'force-always-relay', 'allow-websocket', 'allow-insecure-tls']

def tunnel_profile(transport):
    prefix = 'vless-'+transport+'-'
    return {'server': options.get(prefix+'server', ''), 'port': options.get(prefix+'port', '443'), 'uuid': options.get(prefix+'uuid', ''), 'server_name': options.get(prefix+'sni', '')}

current = {'version': 4, 'server': {'host': options.get('custom-rendezvous-server', ''), 'relay': options.get('relay-server', ''), 'api': options.get('api-server', ''), 'key': options.get('key', '')}, 'network': {key: options.get(key, '') for key in network_keys}, 'proxy': {'address': config.get('socks', {}).get('proxy', ''), 'username': config.get('socks', {}).get('username', ''), 'password': config.get('socks', {}).get('password', '')}, 'vless': {**vless, 'enabled': 'Y' if vless.get('enabled') else 'N', 'transport': options.get('vless-transport', 'tls'), 'tls_profile': tunnel_profile('tls'), 'reality_profile': tunnel_profile('reality'), **{'reality_'+key.replace('-','_'): options.get('vless-reality-'+key, '') for key in ['public-key','short-id','fingerprint','flow']}}, 'ssh': {**ssh, 'enabled': 'Y' if ssh.get('enabled') else 'N'}}
if current['ssh'].get('server'):
    current['ssh'].setdefault('port',2222)
(folder/'rustdesk-current-network-backup.json').write_text(json.dumps(current,indent=2)+'\n',encoding='utf-8')
p = json.loads((folder/'vps3-client-settings.json').read_text())
active = {'server':p['address'], 'port':'443', 'uuid':p['uuid'], 'server_name':p['sni']}
vps3 = {'version':4, 'server': {'host':p['address'], 'relay':p['address'], 'api':'', 'key':p['rustdesk_key']}, 'network':{'disable-udp':'Y','force-always-relay':'Y','allow-websocket':'N','allow-insecure-tls':'N'}, 'proxy':{'address':'','username':'','password':''}, 'vless': {**active,'enabled':'Y','transport':'reality','reality_public_key':p['public_key'],'reality_short_id':p['short_id'],'reality_fingerprint':p['fingerprint'],'reality_flow':p['flow'],'reality_profile':active}}
(folder/'rustdesk-vps3-reality.json').write_text(json.dumps(vps3,indent=2)+'\n',encoding='utf-8')
for profile in [current,vps3]:
    assert profile['version']==4 and set(profile['server'])=={'host','relay','api','key'}
    assert 'private_key' not in profile.get('server',{})
assert vps3['vless']['uuid'] and vps3['vless']['reality_public_key'] and vps3['vless']['reality_short_id']
print('Importable VPS3 profile and current network backup generated; no device/password reset')
