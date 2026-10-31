"""Generate separate JSON companions; no profile enters the installer payload."""
import argparse
import json
import os
from pathlib import Path
import tomllib

parser = argparse.ArgumentParser()
parser.add_argument('--output-dir', required=True)
parser.add_argument('--basename', required=True)
parser.add_argument('--config', default=str(Path(os.environ['APPDATA'])/'RustDesk/config/RustDesk2.toml'))
parser.add_argument('--vps3', default='')
args = parser.parse_args()
output = Path(args.output_dir)
output.mkdir(parents=True, exist_ok=True)
current = None
network_keys = ['disable-udp', 'force-always-relay', 'allow-websocket', 'allow-insecure-tls']

def write_profile(suffix, profile):
    assert profile['version'] == 4
    assert set(profile['server']) == {'host','relay','api','key'}
    path = output/(args.basename+'.'+suffix+'.json')
    path.write_text(json.dumps(profile,indent=2)+'\n',encoding='utf-8')
    print('NETWORK JSON:', path.name)

example = {'version':4, 'server':{'host':'server.example','relay':'server.example','api':'','key':''}, 'network':{key:'N' for key in network_keys}, 'proxy':{'address':'','username':'','password':''}, 'vless':{'server':'server.example','port':'443','uuid':'','server_name':'server.example','enabled':'N','transport':'tls','reality_public_key':'','reality_short_id':'','reality_fingerprint':'chrome','reality_flow':'xtls-rprx-vision','tls_profile':{'server':'server.example','port':'443','uuid':'','server_name':'server.example'},'reality_profile':{'server':'server.example','port':'443','uuid':'','server_name':'target.example'}}, 'ssh':{'server':'server.example','port':'2222','username':'rustdesk','public_key':'','private_key':'','enabled':'N'}}
write_profile('example',example)
source = Path(args.config)
if source.exists():
    cfg = tomllib.loads(source.read_text(encoding='utf-8'))
    opt = cfg.get('options',{})
    vl, ssh, socks = cfg.get('vless',{}), cfg.get('ssh',{}), cfg.get('socks',{})
    def profile(mode):
        prefix='vless-'+mode+'-'
        return {'server':opt.get(prefix+'server',''),'port':opt.get(prefix+'port','443'),'uuid':opt.get(prefix+'uuid',''),'server_name':opt.get(prefix+'sni','')}
    current={'version':4,'server':{'host':opt.get('custom-rendezvous-server',''),'relay':opt.get('relay-server',''),'api':opt.get('api-server',''),'key':opt.get('key','')},'network':{key:opt.get(key,'') for key in network_keys},'proxy':{'address':socks.get('proxy',''),'username':socks.get('username',''),'password':socks.get('password','')},'vless':{**vl,'enabled':'Y' if vl.get('enabled') else 'N','transport':opt.get('vless-transport','tls'),'tls_profile':profile('tls'),'reality_profile':profile('reality'),**{'reality_'+key.replace('-','_'):opt.get('vless-reality-'+key,'') for key in ['public-key','short-id','fingerprint','flow']}},'ssh':{**ssh,'enabled':'Y' if ssh.get('enabled') else 'N'}}
    if opt.get('network-profile-base-server'):
        current['server'].update(json.loads(opt['network-profile-base-server']))
    if current['ssh'].get('server'):
        current['ssh'].setdefault('port',2222)
    write_profile('current-network',current)
if args.vps3 and Path(args.vps3).exists():
    p=json.loads(Path(args.vps3).read_text())
    active={'server':p['address'],'port':'443','uuid':p['uuid'],'server_name':p['sni']}
    vps3_server={'host':p['address'],'relay':p['address'],'api':'','key':p['rustdesk_key']}
    reality={**active,'rustdesk_server':vps3_server}
    real_vless={**active,'enabled':'Y','transport':'reality','reality_public_key':p['public_key'],'reality_short_id':p['short_id'],'reality_fingerprint':p['fingerprint'],'reality_flow':p['flow'],'reality_profile':reality}
    write_profile('vps3-reality',{'version':4,'server':vps3_server,'network':{'disable-udp':'Y','force-always-relay':'Y','allow-websocket':'N','allow-insecure-tls':'N'},'proxy':{'address':'','username':'','password':''},'vless':real_vless})
    if current is not None:
        combined=json.loads(json.dumps(current))
        combined['vless'].update(real_vless)
        combined['network'].update({'disable-udp':'Y','force-always-relay':'Y','allow-websocket':'N'})
        if not combined['ssh'].get('server') or not combined['ssh'].get('private_key'):
            identity=Path(os.environ.get('RD_SSHKEY_DIR', r'D:\RD\work\rustdesk-ssh\.sshkeys'))/'id_ed25519'
            if identity.is_file() and identity.with_suffix('.pub').is_file():
                combined['ssh']={'server':combined['server']['host'],'port':'2222','username':'rustdesk','public_key':identity.with_suffix('.pub').read_text().strip(),'private_key':identity.read_text(),'enabled':'N'}
        combined['ssh']['enabled']='N'
        write_profile('vps1-vps3-network',combined)
