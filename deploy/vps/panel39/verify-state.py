import argparse
import json
from pathlib import Path
import sqlite3
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('backup_root', type=Path)
parser.add_argument('--backup-check', action='store_true')
args = parser.parse_args()
def connect(path):
    return sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)

for relative in ('data/db_v2.sqlite3', 'x-ui-data/x-ui.db'):
    with connect(args.backup_root / relative) as db:
        assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
print('PASS stopped-state backup database integrity')
if args.backup_check:
    raise SystemExit(0)
with connect(args.backup_root / 'x-ui-data/x-ui.db') as old, connect(Path('/opt/rustdesk-server/x-ui-data/x-ui.db')) as new:
    assert new.execute('pragma integrity_check').fetchone()[0] == 'ok'
    query = 'select id,port,protocol,settings,stream_settings from inbounds order by id'
    assert old.execute(query).fetchall() == new.execute(query).fetchall(), 'Inbound/client parameters changed'
    assert old.execute('select * from users').fetchall() == new.execute('select * from users').fetchall(), 'Panel authentication changed'
    routing_query = "select value from settings where key='xrayTemplateConfig'"
    assert old.execute(routing_query).fetchall() == new.execute(routing_query).fetchall(), 'Routing template changed'
    row = new.execute("select value from settings where key='webBasePath'").fetchone()
    path = row[0] if row else '/'
status = subprocess.check_output(['docker', 'exec', 'rustdesk-server', 'curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}', 'http://127.0.0.1:2053/' + path.strip('/') + '/']).decode()
assert status == '200', 'Panel HTTP ' + status
subprocess.run(['docker', 'exec', 'rustdesk-server', '/usr/bin/healthcheck-combined.sh'], check=True)
subprocess.run(['docker', 'exec', 'rustdesk-server', '/app/bin/xray-linux-amd64', 'run', '-test', '-config', '/app/bin/config.json'], check=True)
print('PASS production panel, authentication, clients, routing, services and database')
