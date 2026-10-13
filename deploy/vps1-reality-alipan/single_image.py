"""Preserve the live Xray patch, repackage one Docker image, guarded cutover."""
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

ROOT=Path('/root/rustdesk-vless-stack-canary-20260929-1020/docker-combined')
BASE=Path('/var/backups/rustdesk-single-image')
TAG='rustdesk-server-combined:complete-20261003'
NAME='rustdesk-server'

def run(args, timeout=120, check=True):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if check and p.returncode:
        raise RuntimeError('command failed: '+args[0]+' '+args[1]+' exit '+str(p.returncode))
    return p

def docker(*args, **kw):return run(['docker']+list(args),**kw)
def inspect():return json.loads(docker('inspect',NAME).stdout)[0]
def save(path,data):
    path.write_text(json.dumps(data,indent=2)+'\n');os.chmod(str(path),0o600)
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
    return h.hexdigest()
def compose(*args):return run(['docker','compose','--project-directory',str(ROOT),'-f',str(ROOT/'docker-compose.yml')]+list(args))
def corehash():return docker('exec',NAME,'sha256sum','/app/bin/xray-linux-amd64').stdout.decode().split()[0]
def runtime():return json.loads(docker('exec',NAME,'cat','/app/bin/config.json').stdout)
def healthy():
    for unused in range(60):
        c=inspect()
        if c['State'].get('Health',{}).get('Status')=='healthy':return
        if not c['State'].get('Running'):raise RuntimeError('container stopped')
        time.sleep(1)
    raise RuntimeError('health check timeout')

def prepare():
    os.umask(0o077)
    c=inspect()
    if c['State'].get('Health',{}).get('Status')!='healthy':raise RuntimeError('baseline unhealthy')
    if c['HostConfig']['NetworkMode']!='host':raise RuntimeError('unexpected network mode')
    if len(docker('ps','-aq').stdout.decode().split())!=1:raise RuntimeError('unexpected other containers')
    folder=BASE/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True,mode=0o700)
    save(folder/'container-before.json',c)
    save(folder/'runtime-before.json',runtime())
    images=json.loads(docker('image','inspect',*docker('image','ls','-aq','--no-trunc').stdout.decode().split()).stdout)
    save(folder/'images-before.json',images)
    oldtag=c['Config']['Image']
    for name in ('docker-compose.yml','.env'):
        (folder/name).write_bytes((ROOT/name).read_bytes())
    docker('cp',NAME+':/app/bin/xray-linux-amd64',str(folder/'xray-linux-amd64'))
    docker('cp',NAME+':/root/.config/rustdesk',str(folder/'runtime-config'))
    os.chmod(str(folder/'xray-linux-amd64'),0o755)
    oldhash=corehash()
    if digest(folder/'xray-linux-amd64')!=oldhash:raise RuntimeError('copied core differs')
    # Online copy for certificates and an additional data snapshot; stopped copy follows at cutover.
    sources=[x['Source'] for x in c['Mounts']]
    run(['tar','-czf',str(folder/'mounts-online.tar.gz')]+sources,timeout=120)
    print('Saving original complete image archive',flush=True)
    docker('image','save','-o',str(folder/'original-image.tar'),oldtag)
    (folder/'Dockerfile').write_text('FROM '+oldtag+'\nCOPY xray-linux-amd64 /app/bin/xray-linux-amd64\nRUN chmod 755 /app/bin/xray-linux-amd64\n')
    print('Building image with the verified live core patch',flush=True)
    result=docker('build','--network=none','-t',TAG,'-f',str(folder/'Dockerfile'),str(folder),timeout=180)
    (folder/'build.log').write_bytes(result.stdout+result.stderr)
    docker('image','save','-o',str(folder/'complete-image.tar'),TAG)
    # No container uses this candidate. Reload only the final image from the archive.
    docker('image','rm',TAG)
    docker('image','load','-i',str(folder/'complete-image.tar'))
    candidate=json.loads(docker('image','inspect',TAG).stdout)[0]
    if candidate.get('Parent'):raise RuntimeError('loaded final image still has a parent')
    check=docker('run','--rm','--network=none','--entrypoint','sha256sum',TAG,'/app/bin/xray-linux-amd64')
    if check.stdout.decode().split()[0]!=oldhash:raise RuntimeError('candidate core mismatch')
    oldimage=next(x for x in images if x['Id']==c['Image'])
    for field in ('Entrypoint','Cmd','Env','Healthcheck','WorkingDir','User','ExposedPorts'):
        if candidate['Config'].get(field)!=oldimage['Config'].get(field):raise RuntimeError('image config drift: '+field)
    save(folder/'state.json',{'status':'prepared','folder':str(folder),'oldtag':oldtag,'oldid':c['Image'],'newtag':TAG,'newid':candidate['Id'],'core_sha256':oldhash,'original_archive_sha256':digest(folder/'original-image.tar'),'complete_archive_sha256':digest(folder/'complete-image.tar')})
    BASE.mkdir(exist_ok=True);save(BASE/'active.json',{'folder':str(folder)})
    print(json.dumps({'prepared':True,'backup':str(folder),'candidate_parent_empty':True,'patched_core_preserved':True}),flush=True)

def verify(folder):
    healthy()
    state=json.loads((folder/'state.json').read_text())
    if corehash()!=state['core_sha256']:raise RuntimeError('production core mismatch')
    before=json.loads((folder/'runtime-before.json').read_text())
    if runtime()!=before:raise RuntimeError('production routing changed')
    current=inspect();old=json.loads((folder/'container-before.json').read_text())
    if sorted(current['Config']['Env'])!=sorted(old['Config']['Env']):raise RuntimeError('container environment changed')
    for k in ('NetworkMode','CapAdd','SecurityOpt','RestartPolicy'):
        if current['HostConfig'][k]!=old['HostConfig'][k]:raise RuntimeError('host config drift: '+k)
    expected=set(old['HostConfig']['Binds'])
    actual=set(current['HostConfig']['Binds'])
    if not expected.issubset(actual):raise RuntimeError('original mount missing')
    copied=docker('exec',NAME,'sha256sum','/root/.config/rustdesk/RustDesk.toml').stdout.decode().split()[0]
    if copied!=digest(folder/'runtime-config'/'RustDesk.toml'):raise RuntimeError('server config changed')
    sys.path.insert(0,'/opt/rustdesk-tls-fallback')
    import migrate_reality_alipan as m
    p=json.loads(Path('/var/lib/rustdesk-reality-alipan/client-parameters-private.json').read_text())
    i=next(x for x in before['inbounds'] if x.get('port')==19443)
    audit=m.MOUNT/('single-image-probe-'+uuid.uuid4().hex[:8]);audit.mkdir(mode=0o700)
    m.test_clients(audit,i,p['public_key'],p['short_id'],'203.0.113.10',443,'single-image')
    for port in (8443,18444,19443,2053,22115,22116,22117,2222):
        if not m.port_open(port):raise RuntimeError('listener missing: '+str(port))
    print('PASS: health, exact routing/environment, core hash, REALITY registration/relay/user routes and all gateway listeners',flush=True)

def cutover():
    os.umask(0o077)
    folder=Path(json.loads((BASE/'active.json').read_text())['folder'])
    state=json.loads((folder/'state.json').read_text())
    if state['status']!='prepared':raise RuntimeError('wrong state')
    if inspect()['Image']!=state['oldid']:raise RuntimeError('production changed since preparation')
    if (ROOT/'.env').read_bytes()!=(folder/'.env').read_bytes() or (ROOT/'docker-compose.yml').read_bytes()!=(folder/'docker-compose.yml').read_bytes():raise RuntimeError('compose drift')
    if (ROOT/'runtime-config').exists():raise RuntimeError('runtime config directory already exists')
    import shutil
    shutil.copytree(str(folder/'runtime-config'),str(ROOT/'runtime-config'))
    env=(ROOT/'.env').read_text()
    lines=[x for x in env.splitlines() if not x.startswith('IMAGE_TAG=')]
    (ROOT/'.env').write_text('\n'.join(lines)+'\nIMAGE_TAG='+TAG+'\n')
    composefile=(ROOT/'docker-compose.yml').read_text()
    needle='      - ./data:/data\n'
    if composefile.count(needle)!=1:raise RuntimeError('unexpected volume template')
    (ROOT/'docker-compose.yml').write_text(composefile.replace(needle,needle+'      - ./runtime-config:/root/.config/rustdesk\n'))
    try:
        rendered=json.loads(compose('config','--format','json').stdout)['services']['rustdesk-server']
        if rendered['image']!=TAG or rendered['container_name']!=NAME:raise RuntimeError('compose render mismatch')
        print('Stopping RustDesk briefly and taking a consistent mounted-data backup',flush=True)
        docker('stop','-t','30',NAME)
        sources=[x['Source'] for x in json.loads((folder/'container-before.json').read_text())['Mounts']]
        run(['tar','-czf',str(folder/'mounts-stopped.tar.gz')]+sources)
        state['downtime_started']=time.time();save(folder/'state.json',state)
        compose('up','-d','--no-build','--force-recreate','rustdesk-server')
        verify(folder)
        state['status']='verified';state['downtime_finished']=time.time();save(folder/'state.json',state)
        print(json.dumps({'cutover_verified':True,'backup':str(folder)}),flush=True)
    except BaseException:
        print('Verification failed; restoring previous configuration and patched container',flush=True)
        (ROOT/'.env').write_bytes((folder/'.env').read_bytes())
        (ROOT/'docker-compose.yml').write_bytes((folder/'docker-compose.yml').read_bytes())
        if docker('image','inspect',state['oldtag'],check=False).returncode:docker('image','load','-i',str(folder/'original-image.tar'))
        docker('stop','-t','30',NAME,check=False)
        compose('create','--no-build','--force-recreate','rustdesk-server')
        docker('cp',str(folder/'xray-linux-amd64'),NAME+':/app/bin/xray-linux-amd64')
        docker('cp',str(folder/'runtime-config'),NAME+':/root/.config/rustdesk')
        compose('start','rustdesk-server');healthy()
        state['status']='rolled_back';save(folder/'state.json',state)
        raise

def cleanup():
    folder=Path(json.loads((BASE/'active.json').read_text())['folder'])
    state=json.loads((folder/'state.json').read_text())
    if state['status']!='verified' or inspect()['Image']!=state['newid']:raise RuntimeError('unverified production')
    if digest(folder/'original-image.tar')!=state['original_archive_sha256'] or digest(folder/'complete-image.tar')!=state['complete_archive_sha256']:raise RuntimeError('archive checksum changed')
    protected={json.loads(docker('inspect',x).stdout)[0]['Image'] for x in docker('ps','-aq').stdout.decode().split()}
    images=json.loads((folder/'images-before.json').read_text())
    allowed={x['Id'] for x in images}
    if state['newid'] in allowed:raise RuntimeError('new image collides with cleanup targets')
    # Explicit original image IDs only; never force removal or prune unrelated assets.
    todo=[state['oldid']]+[x['Id'] for x in images if x['Id']!=state['oldid']]
    deleted=[]
    for image in todo:
        if image in protected:raise RuntimeError('old image still referenced by container')
        if docker('image','inspect',image,check=False).returncode:continue
        result=docker('image','rm',image,check=False)
        if result.returncode:raise RuntimeError('dependency cleanup refused for '+image[:19])
        deleted.append(image)
    remaining=docker('image','ls','-aq','--no-trunc').stdout.decode().split()
    if set(remaining)!={state['newid']}:raise RuntimeError('unexpected remaining image records')
    healthy()
    state['status']='complete';state['removed_image_records']=deleted;save(folder/'state.json',state)
    print(json.dumps({'complete':True,'image':TAG,'remaining_image_records':len(set(remaining)),'backup':str(folder),'healthy':True}),flush=True)

if __name__=='__main__':
    {'prepare':prepare,'cutover':cutover,'cleanup':cleanup}[sys.argv[1]]()
