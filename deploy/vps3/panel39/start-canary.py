"""Run on VPS3; copy secrets only into a protected test directory, not image."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone

os.umask(0o077)
source = Path('/opt/rustdesk-server')
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
target = Path('/opt/rustdesk-build') / ('panel39-test-' + stamp)
target.mkdir(mode=0o700)
for folder in ('data', 'x-ui-data', 'x-ui-acme', 'internal-tls'):
    shutil.copytree(source / folder, target / folder,
                    ignore=shutil.ignore_patterns('*-wal', '*-shm'))
for filename in ('compose.yml', '.env'):
    if (source / filename).exists():
        shutil.copy2(source / filename, target / filename)
for relative in ('data/db_v2.sqlite3', 'x-ui-data/x-ui.db'):
    with sqlite3.connect('file:' + str(source / relative) + '?mode=ro', uri=True) as live:
        with sqlite3.connect(target / relative) as snapshot:
            live.backup(snapshot)
            assert snapshot.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
with sqlite3.connect(target / 'x-ui-data/x-ui.db') as database:
    baseline = database.execute('select count(*) from inbounds').fetchone()[0]
    (target / 'baseline.json').write_text(json.dumps({'inbounds': baseline}))
metadata = json.loads(subprocess.check_output(['docker', 'inspect', 'rustdesk-server']))[0]
env_file = target / 'container.env'
env_file.write_text('\n'.join(metadata['Config']['Env']) + '\n')
args = ['docker', 'run', '-d', '--name', 'rustdesk-panel39-canary',
        '--network', 'bridge', '--env-file', str(env_file),
        '--security-opt', 'no-new-privileges:true']
for folder, destination in (('data', '/data'), ('x-ui-data', '/etc/x-ui'),
                            ('x-ui-acme', '/root/.acme.sh')):
    args += ['-v', str(target / folder) + ':' + destination]
for name, destination in (('fullchain.pem', '/run/tls/fullchain.pem'),
                           ('privkey.pem', '/run/tls/privkey.pem')):
    args += ['-v', str(target / 'internal-tls' / name) + ':' + destination + ':ro']
args += ['rustdesk-server-combined:panel-3.9.0-candidate']
subprocess.run(args, check=True)
print('Protected test snapshot:', target)
print('Baseline inbound count:', baseline)
print('No host port is published; production is unchanged.')
