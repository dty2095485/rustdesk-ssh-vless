"""Disable the legacy gateway and persist the s6 bundle/healthcheck override."""
import json,os,socket,subprocess,time,uuid
from pathlib import Path

ROOT=Path('/root/rustdesk-vless-stack-canary-20260929-1020/docker-combined')
def run(args,check=True):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40)
    if check and p.returncode:raise RuntimeError('command failed: '+args[0]+' '+args[1])
    return p
def d(*args,**kw):return run(['docker']+list(args),**kw)
def listener(port):
    try:
        with socket.create_connection(('127.0.0.1',port),1):return True
    except OSError:return False
def pid(service):
    return d('exec','rustdesk-server','/package/admin/s6/command/s6-svstat','-p','/run/s6-rc/servicedirs/'+service).stdout

def main():
    os.umask(0o077)
    compose=ROOT/'docker-compose.yml';original=compose.read_bytes()
    bundle=ROOT/'s6-user-contents';health=ROOT/'healthcheck-active.sh'
    if bundle.exists() or health.exists():raise RuntimeError('override paths already exist; inspect first')
    backup=Path('/var/backups/rustdesk-single-image')/('disable-hbvless-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);backup.mkdir(mode=0o700)
    (backup/'docker-compose.yml').write_bytes(original)
    d('cp','rustdesk-server:/etc/s6-overlay/s6-rc.d/user/contents.d',str(bundle))
    d('cp','rustdesk-server:/usr/bin/healthcheck-combined.sh',str(backup/'healthcheck-before.sh'))
    (backup/'hbvless').write_bytes((bundle/'hbvless').read_bytes())
    # Exactly one legacy service marker; retain every other startup service.
    marker=bundle/'hbvless'
    if marker.parent.resolve()!=bundle.resolve() or not marker.is_file():raise RuntimeError('unexpected marker')
    marker.unlink()
    oldhealth=(backup/'healthcheck-before.sh').read_text()
    h=oldhealth.replace('for service in hbbs hbbr hbvless hbssh reality-ui; do','for service in hbbs hbbr hbssh reality-ui; do')
    h=h.replace('21118 21119 8443 2053','21118 21119 18444 19443 2053')
    if h==oldhealth or 'hbvless' in h or '8443' in h:raise RuntimeError('unexpected healthcheck template')
    health.write_text(h);os.chmod(str(health),0o755)
    text=original.decode();needle='      - ./runtime-config:/root/.config/rustdesk\n'
    if text.count(needle)!=1:raise RuntimeError('compose volume template changed')
    new=text.replace(needle,needle+'      - ./s6-user-contents:/etc/s6-overlay/s6-rc.d/user/contents.d:ro\n      - ./healthcheck-active.sh:/usr/bin/healthcheck-combined.sh:ro\n')
    services=('hbbs','hbbr','hbssh','reality-ui')
    before={name:pid(name) for name in services}
    try:
        compose.write_text(new)
        run(['docker','compose','--project-directory',str(ROOT),'-f',str(compose),'config','--quiet'])
        # Update the current writable layer too: docker restart keeps this state;
        # a future Compose recreation gets the host-mounted overrides instead.
        d('cp',str(health),'rustdesk-server:/usr/bin/healthcheck-combined.sh')
        d('exec','rustdesk-server','rm','/etc/s6-overlay/s6-rc.d/user/contents.d/hbvless')
        d('exec','rustdesk-server','/command/s6-svc','-d','-wD','-T','10000','/run/service/hbvless')
        if listener(8443):raise RuntimeError('8443 still listening')
        for name in services:
            if pid(name)!=before[name]:raise RuntimeError('unrelated service restarted: '+name)
        d('exec','rustdesk-server','/usr/bin/healthcheck-combined.sh')
        for unused in range(20):
            state=json.loads(d('inspect','rustdesk-server').stdout)[0]['State']
            if state.get('Health',{}).get('Status')=='healthy':break
            time.sleep(1)
        if state.get('Health',{}).get('Status')!='healthy':raise RuntimeError('container unhealthy')
        result={'complete':True,'legacy_8443_listening':False,'other_service_pids_unchanged':True,'healthy':True,'persistent_on_restart_and_compose_recreate':True,'backup':str(backup)}
        (backup/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    except BaseException:
        compose.write_bytes(original)
        d('cp',str(backup/'healthcheck-before.sh'),'rustdesk-server:/usr/bin/healthcheck-combined.sh')
        d('cp',str(backup/'hbvless'),'rustdesk-server:/etc/s6-overlay/s6-rc.d/user/contents.d/hbvless')
        d('exec','rustdesk-server','/command/s6-svc','-u','/run/service/hbvless')
        print('Restored the original startup marker, healthcheck and Compose',flush=True);raise

if __name__=='__main__':main()
