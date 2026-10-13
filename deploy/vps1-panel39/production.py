"""Guarded VPS1 image replacement; preserve databases for reversible migration."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path('/root/rustdesk-vless-stack-canary-20260929-1020/docker-combined')
BASE = Path('/var/backups/rustdesk-panel39')
TAG = 'rustdesk-server-combined:official-3.9.0-20261004'
CORE_HASH = '96efb28b8b2086275598dc46e73b5dc340da948b4e1ccc4f1719f83f67b793a7'
os.umask(0o077)

def docker(*args):
    return subprocess.check_output(['docker'] + list(args))
def inspect():
    return json.loads(docker('inspect', 'rustdesk-server'))[0]
def save(path, value):
    path.write_text(json.dumps(value, indent=2))
def compose():
    subprocess.check_call(['docker', 'compose', '--project-directory', str(ROOT), '-f', str(ROOT / 'docker-compose.yml'), 'up', '-d', '--no-build', '--pull', 'never'])
def health():
    for unused in range(40):
        meta = inspect()
        if meta['State'].get('Health', {}).get('Status') == 'healthy':
            return
        if not meta['State']['Running']:
            raise RuntimeError('Container stopped')
        time.sleep(1)
    raise RuntimeError('Health timeout')
def runtime():
    return json.loads(docker('exec', 'rustdesk-server', 'cat', '/app/bin/config.json'))
def verify(folder):
    health()
    assert docker('exec', 'rustdesk-server', 'sha256sum', '/app/bin/xray-linux-amd64').decode().split()[0] == CORE_HASH
    before = json.loads((folder / 'runtime-before.json').read_text())
    assert runtime() == before, 'Generated Xray routing/configuration changed'
    old = json.loads((folder / 'container-before.json').read_text())
    current = inspect()
    assert set(current['HostConfig']['Binds']) == set(old['HostConfig']['Binds']), 'Mounts changed'
    for key in ('NetworkMode', 'RestartPolicy', 'SecurityOpt', 'CapAdd'):
        assert current['HostConfig'][key] == old['HostConfig'][key], 'Host configuration changed: ' + key
    old_db = next(x for x in old['Mounts'] if x['Destination'] == '/etc/x-ui')
    index = old['Mounts'].index(old_db)
    with sqlite3.connect(str(folder / 'mounts' / str(index) / 'x-ui.db')) as a, sqlite3.connect(old_db['Source'] + '/x-ui.db') as b:
        assert b.execute('pragma integrity_check').fetchone()[0] == 'ok'
        for query in ('select id,port,listen,protocol,settings,stream_settings from inbounds order by id',
                      'select * from users', "select value from settings where key='webBasePath'"):
            assert a.execute(query).fetchall() == b.execute(query).fetchall(), 'Database settings changed'
        path = b.execute("select value from settings where key='webBasePath'").fetchone()[0]
    status = docker('exec', 'rustdesk-server', 'curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}',
                    '--resolve', 'rd.example.com:2053:127.0.0.1', 'https://rd.example.com:2053/' + path.strip('/') + '/').decode()
    assert status == '200', 'Panel HTTPS check failed'
    docker('exec', 'rustdesk-server', '/usr/bin/healthcheck-combined.sh')
    subprocess.check_call(['python3', '/opt/rustdesk-build/panel39/verify-routes.py'])
    print('PASS production official core, exact routes/authentication/mounts, panel HTTPS and all REALITY users', flush=True)
def rollback(folder):
    folder = folder.resolve()
    assert folder.parent == BASE and folder.is_dir(), 'Invalid backup directory'
    old = json.loads((folder / 'container-before.json').read_text())
    save(folder / 'failed-container.json', inspect())
    docker('stop', '-t', '30', 'rustdesk-server')
    failed = folder / 'failed-state'
    failed.mkdir()
    for index, mount in enumerate(old['Mounts']):
        if not mount['RW']:
            continue
        source = Path(mount['Source']).resolve()
        assert ROOT in source.parents, 'Unexpected writable mount outside deployment'
        shutil.move(str(source), str(failed / str(index)))
        shutil.copytree(str(folder / 'mounts' / str(index)), str(source))
    for name in ('docker-compose.yml', '.env'):
        shutil.copy2(str(folder / name), str(ROOT / name))
    compose()
    health()
    assert inspect()['Image'] == old['Image']
    print('ROLLED BACK image AND stopped-state database:', folder, flush=True)
def switch():
    old = inspect()
    assert old['Image'] == 'sha256:9b8ff0c6c43a2375a4b3481b79ef1fa95b4d9edb4368fbad14cda651e6420fdb', 'Production changed since audit'
    assert old['State']['Health']['Status'] == 'healthy'
    docker('image', 'inspect', TAG)
    assert docker('run', '--rm', '--network', 'none', '--entrypoint', 'sha256sum', TAG, '/app/bin/xray-linux-amd64').decode().split()[0] == CORE_HASH
    BASE.mkdir(parents=True, exist_ok=True)
    folder = BASE / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(mode=0o700)
    save(folder / 'container-before.json', old)
    save(folder / 'runtime-before.json', runtime())
    for name in ('docker-compose.yml', '.env'):
        shutil.copy2(str(ROOT / name), str(folder / name))
    with gzip.open(str(folder / 'old-image.tar.gz'), 'wb', compresslevel=1) as archive:
        process = subprocess.Popen(['docker', 'image', 'save', old['Config']['Image']], stdout=subprocess.PIPE)
        shutil.copyfileobj(process.stdout, archive)
        process.stdout.close()
        assert process.wait() == 0, 'Image backup failed'
    print('BACKUP_DIRECTORY=' + str(folder), flush=True)
    docker('stop', '-t', '30', 'rustdesk-server')
    try:
        (folder / 'mounts').mkdir()
        for index, mount in enumerate(old['Mounts']):
            source = Path(mount['Source'])
            dest = folder / 'mounts' / str(index)
            if source.is_dir():
                shutil.copytree(str(source), str(dest))
                for name in ('x-ui.db', 'db_v2.sqlite3'):
                    if (dest / name).exists():
                        with sqlite3.connect(str(dest / name)) as db:
                            assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
            else:
                shutil.copy2(str(source), str(dest))
    except Exception:
        docker('start', 'rustdesk-server')
        raise
    try:
        env_path = ROOT / '.env'
        env = env_path.read_text()
        updated, count = re.subn(r'^IMAGE_TAG=.*$', 'IMAGE_TAG=' + TAG, env, flags=re.MULTILINE)
        assert count == 1, 'Unexpected IMAGE_TAG layout'
        env_path.write_text(updated)
        compose()
        verify(folder)
        save(BASE / 'active.json', {'backup': str(folder), 'image': TAG, 'core_sha256': CORE_HASH, 'status': 'healthy'})
        print('CUTOVER_HEALTHY; BACKUP_DIRECTORY=' + str(folder), flush=True)
    except Exception:
        print('Cutover check failed; rolling back', flush=True)
        rollback(folder)
        raise

if sys.argv[1] == 'switch':
    switch()
elif sys.argv[1] == 'rollback':
    rollback(Path(sys.argv[2]))
elif sys.argv[1] == 'verify':
    verify(Path(json.loads((BASE / 'active.json').read_text())['backup']))
else:
    raise SystemExit('Expected switch, rollback BACKUP, or verify')
