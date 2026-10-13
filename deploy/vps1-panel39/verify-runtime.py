import json
from pathlib import Path
import sqlite3
import subprocess
import sys

name = sys.argv[1] if len(sys.argv) > 1 else 'rustdesk-panel39-canary'
live = json.loads(subprocess.check_output(['docker', 'inspect', 'rustdesk-server']))[0]
test = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
old_path = next(m['Source'] for m in live['Mounts'] if m['Destination'] == '/etc/x-ui')
new_path = next(m['Source'] for m in test['Mounts'] if m['Destination'] == '/etc/x-ui')
with sqlite3.connect(old_path + '/x-ui.db') as old, sqlite3.connect(new_path + '/x-ui.db') as new:
    assert new.execute('pragma integrity_check').fetchone()[0] == 'ok'
    query = 'select id,port,protocol,settings,stream_settings from inbounds order by id'
    assert old.execute(query).fetchall() == new.execute(query).fetchall(), 'Inbound/client/REALITY changed'
    assert old.execute('select * from users').fetchall() == new.execute('select * from users').fetchall(), 'Users changed'
    query = "select value from settings where key='xrayTemplateConfig'"
    assert old.execute(query).fetchall() == new.execute(query).fetchall(), 'Routing template changed'
    path = new.execute("select value from settings where key='webBasePath'").fetchone()[0]
status = subprocess.check_output(['docker', 'exec', name, 'curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}',
                                 '--resolve', 'rd.example.com:2053:127.0.0.1',
                                 'https://rd.example.com:2053/' + path.strip('/') + '/']).decode()
assert status == '200', 'Panel HTTP ' + status
subprocess.check_call(['docker', 'exec', name, '/usr/bin/healthcheck-combined.sh'])
subprocess.check_call(['docker', 'exec', name, '/app/bin/xray-linux-amd64', 'run', '-test', '-config', '/app/bin/config.json'])
print('PASS database, unchanged authentication/client/routes, panel HTTP and supervised services')
