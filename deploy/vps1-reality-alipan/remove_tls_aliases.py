"""Remove only TLS relay destination aliases; preserve three port mappings."""
import copy,json,os,socket,sqlite3,ssl,sys,time,uuid
from pathlib import Path
sys.path.insert(0,'/opt/rustdesk-tls-fallback')
import migrate_reality_alipan as m
import promote as helper

def stop():
    pid=helper.main_xray_pid(required=False)
    m.docker(['/command/s6-svc','-d','-wD','-T','15000','/run/service/reality-ui'])
    if pid is not None and helper.owned_main_xray(pid):m.docker(['kill','-TERM',str(pid)])
    for port in (2053,18444,19443):m.wait_port(port,False)
def start():
    m.docker(['/command/s6-svc','-u','/run/service/reality-ui'])
    for port in (2053,18444,19443):m.wait_port(port,True)

def tls_connect(identity,destination):
    raw=socket.create_connection(('203.0.113.10',443),10);raw.settimeout(10)
    tls=ssl.create_default_context().wrap_socket(raw,server_hostname='nas.example.com')
    host=b'example.com'
    tls.sendall(b'\x00'+uuid.UUID(identity).bytes+b'\x00\x01'+destination.to_bytes(2,'big')+b'\x02'+bytes([len(host)])+host)
    if m.exact(tls,2)!=b'\x00\x00':raise RuntimeError('legacy TLS response header mismatch')
    return tls

def verify(before,expected,folder):
    if m.runtime()!=expected:raise RuntimeError('unexpected runtime change')
    i=next(x for x in expected['inbounds'] if x.get('port')==18444)
    identity=next(x['id'] for x in i['settings']['clients'] if x['email']=='rustdesk-tls-client')
    for port in (21115,21116):
        with tls_connect(identity,port) as s:
            s.sendall(m.frame(bytes.fromhex('a20100')))
            if not m.recv_frame(s).startswith(bytes.fromhex('aa01')):raise RuntimeError('TLS registration failed')
    payload=m.text_field(1,'tls-cleanup-probe')+m.text_field(2,str(uuid.uuid4()))
    request=m.frame(m.varint((18<<3)|2)+m.varint(len(payload))+payload)
    with tls_connect(identity,21117) as a:
        a.sendall(request)
        with tls_connect(identity,21117) as b:
            b.sendall(request);time.sleep(.25)
            sample=b'TLS-alias-cleanup-test-'*3000
            a.sendall(sample)
            if m.exact(b,len(sample))!=sample:raise RuntimeError('TLS relay forward failed')
            b.sendall(sample)
            if m.exact(a,len(sample))!=sample:raise RuntimeError('TLS relay backward failed')
    # An excluded alias must not produce a valid RustDesk registration reply.
    for port in (443,8443):
        try:
            with tls_connect(identity,port) as s:
                s.sendall(m.frame(bytes.fromhex('a20100')))
                data=s.recv(512)
                if data:raise RuntimeError('excluded alias returned application data')
        except (ConnectionResetError,ssl.SSLEOFError):pass
        except RuntimeError as e:
            if str(e)!='connection ended before response':raise
    reality=copy.deepcopy(next(x for x in expected['inbounds'] if x.get('port')==19443))
    for user in reality['settings']['clients']:
        if user['email']=='rustdesk-reality-client':user['email']='rustdesk-client'
    p=json.loads(Path('/var/lib/rustdesk-reality-alipan/client-parameters-private.json').read_text())
    m.test_clients(folder,reality,p['public_key'],p['short_id'],'203.0.113.10',443,'alias-cleanup')
    print('PASS: legacy TLS registration, bidirectional relay, removed aliases denied; REALITY unchanged and tested',flush=True)

def main():
    os.umask(0o077)
    before=m.runtime();expected=copy.deepcopy(before)
    folder=m.MOUNT/('tls-alias-cleanup-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);folder.mkdir(mode=0o700)
    db=sqlite3.connect(str(m.DB),timeout=15)
    row=db.execute('select id,value from settings where key=?',('xrayTemplateConfig',)).fetchone()
    original=row[1];template=json.loads(original)
    def edit(rules):
        matches=[x for x in rules if x.get('outboundTag')=='rustdesk-tls-21117' and x.get('user')==['rustdesk-tls-client']]
        if len(matches)!=1 or matches[0].get('port')!='21117,443,8443':raise RuntimeError('unexpected baseline relay rule')
        matches[0]['port']='21117'
    edit(expected['routing']['rules']);edit(template['routing']['rules'])
    m.save(folder/'runtime-before.json',before);m.save(folder/'template-before.json',json.loads(original))
    db.execute('BEGIN');dump='\n'.join(db.iterdump());backup=sqlite3.connect(str(folder/'database-before.db'));backup.executescript(dump);backup.close();db.rollback();db.close()
    candidate=copy.deepcopy(expected)
    candidate.pop('metrics',None)
    candidate.pop('api',None)
    candidate['inbounds']=[copy.deepcopy(next(x for x in expected['inbounds'] if x.get('port')==18444))]
    candidate['inbounds'][0]['port']=18544
    candidate['routing']['rules']=[r for r in candidate['routing']['rules'] if r.get('inboundTag')!=['api']]
    if m.port_open(18544):raise RuntimeError('candidate port occupied')
    proc=m.start_core(folder,'candidate',candidate,[18544]);m.stop_core(proc);m.wait_port(18544,False)
    modified=False
    try:
        stop()
        db=sqlite3.connect(str(m.DB),timeout=15)
        with db:
            changed=db.execute('update settings set value=? where id=? and value=?',(json.dumps(template),row[0],original))
            if changed.rowcount!=1:raise RuntimeError('settings changed during preparation')
        db.close();modified=True;start()
        verify(before,expected,folder)
        m.save(folder/'result.json',{'status':'complete','change':'TLS relay rule port 21117,443,8443 -> 21117','tls_rules':4,'reality_rules':2})
        print(json.dumps({'complete':True,'tls_rules':4,'reality_rules':2,'backup':str(folder)}),flush=True)
    except BaseException:
        if modified:
            stop();db=sqlite3.connect(str(m.DB),timeout=15)
            with db:db.execute('update settings set value=? where id=?',(original,row[0]))
            db.close()
        start()
        if m.runtime()!=before:raise RuntimeError('rollback mismatch')
        print('ROLLED BACK original routing',flush=True);raise
    finally:
        for item in list(m.PROCESSES):m.stop_core(item)

if __name__=='__main__':main()
