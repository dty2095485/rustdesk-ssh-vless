import json
from pathlib import Path
import sqlite3
import subprocess

root = Path('/opt/rustdesk-server')
subprocess.run(['docker', 'stop', 'rustdesk-server'], check=True)
with sqlite3.connect(root/'x-ui-data/x-ui.db') as db:
    inbound_id, value = db.execute("SELECT id,stream_settings FROM inbounds WHERE port=443").fetchone()
    stream = json.loads(value)
    reality = stream['realitySettings']
    reality['target'] = 'www.nvidia.com:443'
    reality['serverNames'] = ['www.nvidia.com']
    reality.setdefault('settings', {})['serverName'] = 'www.nvidia.com'
    reality['limitFallbackUpload'] = {'afterBytes': 1048576, 'bytesPerSec': 262144, 'burstBytesPerSec': 524288}
    reality['limitFallbackDownload'] = {'afterBytes': 1048576, 'bytesPerSec': 262144, 'burstBytesPerSec': 524288}
    db.execute('UPDATE inbounds SET stream_settings=? WHERE id=?', (json.dumps(stream), inbound_id))
config = json.loads((root/'client-settings.json').read_text())
config['sni'] = 'www.nvidia.com'
(root/'client-settings.json').write_text(json.dumps(config, indent=2)+'\n')
subprocess.run(['docker', 'compose', 'up', '-d'], cwd=root, check=True)
print('REALITY target updated; authenticated transport has no fallback throttle')
