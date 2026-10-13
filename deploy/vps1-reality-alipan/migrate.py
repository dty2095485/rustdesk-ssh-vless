"""VPS1-only REALITY SNI/port migration, with isolated tests and rollback.

Python 3.6+. No client identities, keys, routing or TLS settings are replaced.
Private artifacts live beside the existing protected x-ui database.
"""
import copy
import hashlib
import http.cookiejar
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import ssl
import struct
import subprocess
import sys
import time
import urllib.request
import uuid

HOST = '203.0.113.10'
SNI = 'www.alipan.com'
PORT = 19443
OLD_TAG = 'in-10443-tcp'
NEW_TAG = 'in-19443-tcp'
MOUNT = Path('/root/rustdesk-vless-stack-canary-20260929-1020/docker-combined/x-ui-data')
DB = MOUNT/'x-ui.db'
CORE = '/app/bin/xray-linux-amd64'
CONTAINER = 'rustdesk-server'
STATE = Path('/var/lib/rustdesk-reality-alipan')
PROCESSES = []
RESULTS = []


def run(args, check=True, timeout=30):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError('command failed: {} (exit {})'.format(args[0], p.returncode))
    return p


def docker(args, **kwargs):
    return run(['docker', 'exec', CONTAINER] + args, **kwargs)


def save(path, data):
    encoded = (json.dumps(data, ensure_ascii=False, indent=2)+'\n').encode()
    temporary = path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    with os.fdopen(os.open(str(temporary), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as f:
        f.write(encoded)
    os.replace(str(temporary), str(path))


def runtime():
    return json.loads(docker(['cat', '/app/bin/config.json']).stdout.decode())


def differences(a, b, path=''):
    if type(a) != type(b): return [path+':type']
    if isinstance(a, dict):
        found=[]
        for k in sorted(set(a)|set(b)):
            p=path+'/'+k
            found.extend([p+':missing'] if k not in a or k not in b else differences(a[k],b[k],p))
        return found
    if isinstance(a, list):
        if len(a)!=len(b): return [path+':length']
        return [p for n,(x,y) in enumerate(zip(a,b)) for p in differences(x,y,path+'/'+str(n))]
    return [] if a==b else [path]


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), 0.5):
            return True
    except OSError:
        return False


def wait_port(port, opened):
    for unused in range(100):
        if port_open(port) == opened:
            return
        time.sleep(0.2)
    raise RuntimeError('listener state not confirmed: '+str(port))


def start_core(folder, name, config, ports):
    host_path = folder/(name+'.json')
    save(host_path, config)
    internal = '/etc/x-ui/'+folder.name+'/'+name
    result = docker([CORE, 'run', '-test', '-c', internal+'.json'], check=False)
    if result.returncode:
        raise RuntimeError('Xray validation failed: '+name)
    log = open(str(folder/(name+'.log')), 'wb')
    shell = 'echo $$ > '+internal+'.pid; exec '+CORE+' run -c '+internal+'.json'
    p = subprocess.Popen(['docker', 'exec', CONTAINER, 'sh', '-c', shell], stdout=log, stderr=log)
    log.close()
    item = (folder/(name+'.pid'), internal+'.json', p)
    PROCESSES.append(item)
    for port in ports:
        wait_port(port, True)
    return item


def stop_core(item):
    pidfile, config_path, process = item
    if pidfile.exists():
        pid = pidfile.read_text().strip()
        if not pid.isdigit():
            raise RuntimeError('invalid owned core PID')
        cmdline = docker(['cat', '/proc/'+pid+'/cmdline'], check=False)
        if cmdline.returncode == 0:
            args = cmdline.stdout.split(b'\0')
            if args[:4] != [CORE.encode(), b'run', b'-c', config_path.encode()]:
                raise RuntimeError('owned process identity changed')
            docker(['kill', '-TERM', pid])
    process.wait(timeout=10)
    PROCESSES.remove(item)


def exact(sock, n):
    data = b''
    while len(data) < n:
        part = sock.recv(n-len(data))
        if not part:
            raise RuntimeError('connection ended before response')
        data += part
    return data


def socks(port, destination, destination_port):
    sock = socket.create_connection(('127.0.0.1', port), 12)
    sock.settimeout(12)
    sock.sendall(b'\x05\x01\x00')
    if exact(sock, 2) != b'\x05\x00':
        raise RuntimeError('SOCKS handshake failed')
    try:
        address = b'\x01'+socket.inet_aton(destination)
    except OSError:
        address = b'\x03'+bytes([len(destination)])+destination.encode()
    sock.sendall(b'\x05\x01\x00'+address+struct.pack('!H', destination_port))
    response = exact(sock, 4)
    if response[1] != 0:
        sock.close()
        raise RuntimeError('SOCKS destination rejected')
    length = {1: 4, 4: 16}.get(response[3])
    if response[3] == 3:
        length = exact(sock, 1)[0]
    if length is None:
        raise RuntimeError('invalid SOCKS response')
    exact(sock, length+2)
    return sock


def frame(payload):
    n = next(x for x in range(1,5) if len(payload) < 1 << (8*x-2))
    return ((len(payload)<<2)|(n-1)).to_bytes(n,'little')+payload


def recv_frame(sock):
    first = exact(sock,1)
    n = (first[0]&3)+1
    size = int.from_bytes(first+exact(sock,n-1),'little')>>2
    if size > 4096:
        raise RuntimeError('unexpected RustDesk response size')
    return exact(sock,size)


def varint(n):
    out = b''
    while n >= 128:
        out += bytes([(n&127)|128]); n >>= 7
    return out+bytes([n])


def text_field(number, text):
    data = text.encode()
    return varint((number<<3)|2)+varint(len(data))+data


def test_clients(folder, inbound, public_key, short_id, address, port, phase):
    ins, outs = [], []
    clients = inbound['settings']['clients']
    for n, client in enumerate(clients):
        tag = 'test-'+str(n)
        ins.append({'tag':tag,'listen':'127.0.0.1','port':10890+n,'protocol':'socks','settings':{'auth':'noauth','udp':False}})
        outs.append({'tag':tag,'protocol':'vless','settings':{'vnext':[{'address':address,'port':port,'users':[{'id':client['id'],'encryption':'none','flow':client.get('flow','')}]}]},'streamSettings':{'network':'raw','security':'reality','realitySettings':{'fingerprint':'chrome','serverName':SNI,'password':public_key,'shortId':short_id,'spiderX':'/'}}})
    config = {'log':{'loglevel':'warning'},'inbounds':ins,'outbounds':outs,'routing':{'rules':[{'type':'field','inboundTag':[o['tag']],'outboundTag':o['tag']} for o in outs]}}
    process = start_core(folder, 'clients-'+phase, config, [10890+n for n in range(len(clients))])
    try:
        for n, client in enumerate(clients):
            local = 10890+n
            email = client['email']
            if email == 'rustdesk-client':
                for target in (22115,22116):
                    with socks(local,'127.0.0.1',target) as sock:
                        sock.sendall(frame(bytes.fromhex('a20100')))
                        if not recv_frame(sock).startswith(bytes.fromhex('aa01')):
                            raise RuntimeError('RustDesk registration test failed')
                pairing = str(uuid.uuid4())
                payload = text_field(1,'alipan-migration-probe')+text_field(2,pairing)
                request = frame(varint((18<<3)|2)+varint(len(payload))+payload)
                with socks(local,'127.0.0.1',22117) as first:
                    first.sendall(request);time.sleep(0.15)
                    with socks(local,'127.0.0.1',22117) as second:
                        second.sendall(request);time.sleep(0.2)
                        sample = b'REALITY-RustDesk-probe-'*3000
                        first.sendall(sample)
                        if exact(second,len(sample)) != sample: raise RuntimeError('relay forward mismatch')
                        second.sendall(sample)
                        if exact(first,len(sample)) != sample: raise RuntimeError('relay backward mismatch')
                try:
                    with socks(local,'127.0.0.1',22) as sock:
                        sock.sendall(b'SSH-2.0-scope-probe\r\n')
                        if sock.recv(512): raise RuntimeError('RustDesk user leaked forbidden destination')
                except (socket.timeout, ConnectionResetError):
                    pass
                except RuntimeError as error:
                    if str(error) != 'SOCKS destination rejected' and str(error) != 'connection ended before response': raise
                RESULTS.append({'phase':phase,'user':email,'registration':True,'relay_bytes_each_way':len(sample),'restricted_destination':True})
            else:
                with socks(local,SNI,443) as raw:
                    ctx = ssl.create_default_context()
                    ctx.set_alpn_protocols(['http/1.1'])
                    with ctx.wrap_socket(raw,server_hostname=SNI) as tls:
                        tls.sendall(('GET / HTTP/1.1\r\nHost: '+SNI+'\r\nConnection: close\r\n\r\n').encode())
                        response=tls.recv(4096)
                        if not response.startswith(b'HTTP/1.'):
                            raise RuntimeError('proxy user did not return real website response')
                        status=int(response.split(b' ')[1])
                        if not 200 <= status < 400: raise RuntimeError('proxy website status '+str(status))
                RESULTS.append({'phase':phase,'user':email,'existing_proxy_route':True,'http_status':status})
        print('PASS '+phase+': all three users, proxy routes, registration, relay and restriction',flush=True)
    finally:
        stop_core(process)
        for n in range(len(clients)): wait_port(10890+n,False)


def api_client():
    base='http://127.0.0.1:18080'
    credentials=json.loads(Path('/var/lib/rustdesk-mux-ui/connection-settings.json').read_text())
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(path,payload=None,token=None):
        headers={'Origin':base,'Content-Type':'application/json'}
        if token: headers['X-CSRF-Token']=token
        req=urllib.request.Request(base+path,headers=headers,data=None if payload is None else json.dumps(payload).encode())
        with opener.open(req,timeout=30) as response: return json.loads(response.read())
    call('/api/login',{'username':credentials['username'],'password':credentials['password']})
    return call


def ui_stop(helper):
    pid=helper.main_xray_pid(required=False)
    docker(['/command/s6-svc','-d','-wD','-T','15000','/run/service/reality-ui'])
    if pid is not None and helper.owned_main_xray(pid): docker(['kill','-TERM',str(pid)])
    for port in (2053,10443,19443,18444): wait_port(port,False)


def ui_start():
    docker(['/command/s6-svc','-u','/run/service/reality-ui'])
    for port in (2053,19443,18444): wait_port(port,True)


def main():
    if os.geteuid()!=0: raise RuntimeError('root required')
    os.umask(0o077)
    STATE.mkdir(mode=0o700,exist_ok=True)
    if (STATE/'active.json').exists(): raise RuntimeError('migration already recorded; inspect before rerun')
    for port in (19443,10890,10891,10892):
        if port_open(port): raise RuntimeError('planned private port occupied: '+str(port))
    baseline=runtime()
    originals=[i for i in baseline['inbounds'] if i.get('tag')==OLD_TAG and i.get('port')==10443]
    if len(originals)!=1: raise RuntimeError('expected one existing REALITY inbound')
    original=originals[0]
    if len(original['settings']['clients'])!=3: raise RuntimeError('expected three users')
    if any(OLD_TAG in r.get('inboundTag',[]) for r in baseline.get('routing',{}).get('rules',[])):
        raise RuntimeError('routing is tied to old inbound tag; review first')
    c=sqlite3.connect(str(DB),timeout=15)
    row=c.execute('SELECT id,port,tag,stream_settings FROM inbounds WHERE port=10443').fetchone()
    if row is None: raise RuntimeError('database inbound missing')
    old_stream=json.loads(row[3]);new_stream=copy.deepcopy(old_stream)
    real=new_stream['realitySettings']
    public_key=real['settings']['publicKey']
    if not public_key: raise RuntimeError('existing public key absent')
    real['target']=SNI+':443';real['serverNames']=[SNI];real['settings']['serverName']=SNI
    short_id=next((s for s in real['shortIds'] if s),'')
    updated=copy.deepcopy(original)
    updated['port']=PORT;updated['tag']=NEW_TAG
    updated['streamSettings']['realitySettings']['target']=real['target']
    updated['streamSettings']['realitySettings']['serverNames']=[SNI]
    folder=MOUNT/('alipan-migration-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    folder.mkdir(mode=0o700)
    save(folder/'runtime-before.json',baseline)
    save(folder/'row-before.json',{'id':row[0],'port':row[1],'tag':row[2],'stream_settings':row[3]})
    # Python 3.6 has no Connection.backup(). Keep a consistent read transaction
    # while taking a logical SQLite snapshot; never copy a live WAL database.
    c.execute('BEGIN')
    dump='\n'.join(c.iterdump())
    backup=sqlite3.connect(str(folder/'database-before.db'))
    backup.executescript(dump);backup.close();c.rollback();c.close()
    sys.path.insert(0,'/opt/rustdesk-tls-fallback')
    import promote as helper
    pids={name:helper.service_pid(name) for name in ('hbbs','hbbr','hbvless','hbssh')}
    candidate={'log':{'loglevel':'warning'},'inbounds':[updated],'outbounds':copy.deepcopy(baseline['outbounds']),'routing':copy.deepcopy(baseline['routing'])}
    candidate['routing']['rules']=[r for r in candidate['routing']['rules'] if r.get('inboundTag')!=['api']]
    server=start_core(folder,'candidate',candidate,[PORT])
    try:
        test_clients(folder,updated,public_key,short_id,'127.0.0.1',PORT,'candidate')
    finally:
        stop_core(server);wait_port(PORT,False)
    call=api_client();state=call('/api/state')
    if state['drift']: raise RuntimeError('mux externally modified')
    next_config=copy.deepcopy(state['config'])
    rules=[r for r in next_config['rules'] if r['sni']=='rd.example.com']
    if len(rules)!=1 or rules[0]['target']!='127.0.0.1:10443': raise RuntimeError('unexpected rd mux rule')
    if any(r['sni']==SNI for r in next_config['rules']): raise RuntimeError('Alipan mux rule already exists')
    rules[0]['target']='127.0.0.1:4443';rules[0]['name']='rd.example.com 面板 HTTPS'
    next_config['rules'].insert(0,{'id':'reality-alipan','name':'阿里云盘 SNI / REALITY','sni':SNI,'alpn':[],'target':'127.0.0.1:'+str(PORT),'enabled':True})
    save(folder/'mux-before.json',state)
    mux_changed=False;database_changed=False
    try:
        print('Candidate passed. Applying reviewed database fields and mux only.',flush=True)
        ui_stop(helper)
        c=sqlite3.connect(str(DB),timeout=15)
        with c:
            cursor=c.execute('UPDATE inbounds SET port=?,tag=?,stream_settings=? WHERE id=? AND port=? AND tag=? AND stream_settings=?',(PORT,NEW_TAG,json.dumps(new_stream),row[0],row[1],row[2],row[3]))
            if cursor.rowcount!=1: raise RuntimeError('database changed during migration')
        c.close();database_changed=True;ui_start()
        actual=runtime()
        save(folder/'runtime-after.json',actual)
        old_normal=copy.deepcopy(baseline);new_normal=copy.deepcopy(actual)
        for config in (old_normal,new_normal):
            for inbound in config['inbounds']:
                if inbound['tag'] in (OLD_TAG,NEW_TAG):
                    inbound['tag']=OLD_TAG;inbound['port']=10443
                    inbound['streamSettings']['realitySettings']['target']='127.0.0.1:4443'
                    inbound['streamSettings']['realitySettings']['serverNames']=['rd.example.com']
            # 3x-ui orders listeners by port. Listener order is not routing order.
            config['inbounds'].sort(key=lambda i:i.get('tag',''))
        if old_normal!=new_normal:
            print('Unexpected config paths: '+', '.join(differences(old_normal,new_normal)[:20]),flush=True)
            raise RuntimeError('unrelated generated config changed')
        applied=call('/api/apply',{'config':next_config,'revision':state['revision']},state['csrf_token'])
        mux_changed=True
        test_clients(folder,updated,public_key,short_id,HOST,443,'public')
        ctx=ssl.create_default_context();ctx.set_alpn_protocols(['h2','http/1.1'])
        with socket.create_connection((HOST,443),12) as raw:
            with ctx.wrap_socket(raw,server_hostname=SNI) as tls:
                if tls.version()!='TLSv1.3': raise RuntimeError('fallback TLS version changed')
                RESULTS.append({'phase':'public','browser_fallback_certificate_valid':True,'alpn':tls.selected_alpn_protocol()})
        meta=json.loads(Path('/var/lib/rustdesk-mux-ui/rd-panel-domain.json').read_text())
        panel_path=meta.get('panel_path') or '/REPLACE_WITH_PANEL_PATH'
        with urllib.request.urlopen('https://rd.example.com'+panel_path,timeout=12) as response:
            if response.status!=200: raise RuntimeError('panel reverse proxy failed')
        for name,pid in pids.items():
            if helper.service_pid(name)!=pid: raise RuntimeError('unrelated RustDesk service restarted')
        if port_open(10443): raise RuntimeError('old REALITY listener still present')
        rustdesk=next(c for c in updated['settings']['clients'] if c['email']=='rustdesk-client')
        save(STATE/'client-parameters-private.json',{'server':HOST,'port':'443','uuid':rustdesk['id'],'server_name':SNI,'public_key':public_key,'short_id':short_id,'fingerprint':'chrome','flow':rustdesk.get('flow',''),'internal_port':PORT})
        save(STATE/'active.json',{'status':'complete','backup':str(folder),'sni':SNI,'internal_port':PORT,'mux_backup':applied['backup_id'],'results':RESULTS,'old_port_closed':True,'panel_verified':True})
        print('PASS production migration: SNI '+SNI+', private port '+str(PORT)+', panel preserved, old port closed.',flush=True)
        print('Protected backup: '+str(folder),flush=True)
    except BaseException:
        rollback_errors=[]
        if mux_changed:
            try:
                current=call('/api/state')
                call('/api/restore',{'id':applied['backup_id'],'revision':current['revision']},current['csrf_token'])
            except Exception as e: rollback_errors.append('mux rollback failed: '+str(e))
        try:
            ui_stop(helper)
            if database_changed:
                c=sqlite3.connect(str(DB),timeout=15)
                with c: c.execute('UPDATE inbounds SET port=?,tag=?,stream_settings=? WHERE id=?',(row[1],row[2],row[3],row[0]))
                c.close()
            docker(['/command/s6-svc','-u','/run/service/reality-ui'])
            for port in (2053,10443,18444): wait_port(port,True)
        except Exception as e: rollback_errors.append('database rollback failed: '+str(e))
        if rollback_errors: raise RuntimeError('; '.join(rollback_errors))
        print('ROLLED BACK: original inbound and mux restored.',flush=True)
        raise


if __name__=='__main__':
    try:
        main()
    finally:
        for item in list(PROCESSES):
            stop_core(item)
