import json
from pathlib import Path
import sqlite3
import subprocess

metadata = json.loads(subprocess.check_output(['docker', 'inspect', 'rustdesk-panel39-canary']))[0]
database_mount = next(mount['Source'] for mount in metadata['Mounts'] if mount['Destination'] == '/etc/x-ui')
target = Path(database_mount).parent
with sqlite3.connect('file:/opt/rustdesk-server/x-ui-data/x-ui.db?mode=ro', uri=True) as old:
    before = old.execute('select id,port,protocol,settings,stream_settings from inbounds order by id').fetchall()
with sqlite3.connect('file:' + str(target / 'x-ui-data/x-ui.db') + '?mode=ro', uri=True) as new:
    assert new.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    after = new.execute('select id,port,protocol,settings,stream_settings from inbounds order by id').fetchall()
    assert before == after, 'Inbound/client/REALITY parameters changed'
    row = new.execute("select value from settings where key='webBasePath'").fetchone()
    path = row[0] if row else '/'
    clients = sum(len(json.loads(row[3]).get('clients', [])) for row in after)
print('PASS database integrity; inbound settings unchanged:', len(after), 'inbound,', clients, 'clients')
status = subprocess.check_output(['docker', 'exec', 'rustdesk-panel39-canary', 'curl',
                                 '-sS', '-o', '/dev/null', '-w', '%{http_code}',
                                 'http://127.0.0.1:2053/' + path.strip('/') + '/']).decode()
assert status == '200', 'Panel page HTTP ' + status
print('PASS panel page HTTP 200 at preserved URI path')
subprocess.run(['docker', 'exec', 'rustdesk-panel39-canary', '/usr/bin/healthcheck-combined.sh'], check=True)
subprocess.run(['docker', 'exec', 'rustdesk-panel39-canary', '/app/bin/xray-linux-amd64',
                'run', '-test', '-config', '/app/bin/config.json'], check=True)
print('PASS all supervised services/listeners and Xray configuration')
