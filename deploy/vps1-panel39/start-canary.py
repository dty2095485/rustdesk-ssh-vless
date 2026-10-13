"""Python 3.6 compatible: test a database copy, never the production mount."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

os.umask(0o077)
meta = json.loads(subprocess.check_output(['docker', 'inspect', 'rustdesk-server']))[0]
target = Path('/opt/rustdesk-build/panel39-test-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
target.mkdir(mode=0o700)
env = target / 'container.env'
env.write_text('\n'.join(meta['Config']['Env']) + '\n')
args = ['docker', 'run', '-d', '--name', 'rustdesk-panel39-canary', '--network', 'bridge',
        '--env-file', str(env), '--security-opt', 'no-new-privileges:true']
for index, mount in enumerate(meta['Mounts']):
    source = Path(mount['Source'])
    dest = target / ('mount-' + str(index))
    if source.is_dir():
        shutil.copytree(str(source), str(dest), ignore=shutil.ignore_patterns('*-wal', '*-shm'))
        for name in ('x-ui.db', 'db_v2.sqlite3'):
            if (source / name).exists():
                subprocess.check_call(['sqlite3', str(source / name), ".backup '" + str(dest / name) + "'"])
    else:
        shutil.copy2(str(source), str(dest))
    if mount['Destination'] == '/etc/x-ui':
        with sqlite3.connect(str(dest / 'x-ui.db')) as db:
            assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
            db.execute("update inbounds set listen='0.0.0.0'")
    args += ['-v', str(dest) + ':' + mount['Destination'] + (':ro' if not mount['RW'] else '')]
args += ['rustdesk-server-combined:official-3.9.0-candidate']
subprocess.check_call(args)
print('Protected isolated test snapshot:', target)
print('Only the COPY inbound listen IP is changed for private bridge tests; no host port published.')
