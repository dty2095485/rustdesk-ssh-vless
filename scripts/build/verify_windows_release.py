import os
"""Reject missing native files or private network defaults in a Windows payload."""
import json
import sys
from pathlib import Path

payload = Path(sys.argv[1])
for name in ['rustdesk.exe', 'librustdesk.dll', 'flutter_windows.dll',
             'dylib_virtual_display.dll', 'xray.exe', 'xray-LICENSE.txt',
             'data/app.so', 'data/icudtl.dat']:
    if not (payload / name).is_file():
        raise SystemExit('Missing payload file: ' + name)
needles = set()
def collect(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if key in {'host', 'relay', 'api', 'server', 'uuid', 'key',
                       'public_key', 'private_key', 'reality_public_key'} and isinstance(value, str) and len(value) > 5:
                if not value.startswith(('127.0.0.1', 'localhost', 'http://127.0.0.1')):
                    needles.add(value)
            collect(value)
    elif isinstance(data, list):
        for value in data:
            collect(value)
profiles = sorted(Path(os.environ.get('RD_PROFILES_DIR', 'D:/RD/releases/windows/ssh')).glob('*network.json'))
if not profiles:
    raise SystemExit('no *network.json profile found to check the payload against')
for profile in profiles:
    collect(json.loads(profile.read_text(encoding='utf-8-sig')))
count = 0
for file in payload.rglob('*'):
    if not file.is_file():
        continue
    if file.suffix.lower() in {'.json', '.toml'} and file.name not in {
            'FontManifest.json', 'AssetManifest.json', 'NativeAssetsManifest.json'}:
        raise SystemExit('Unexpected configuration file in payload: ' + file.name)
    if file.suffix.lower() in {'.exe', '.dll', '.so'}:
        binary = file.read_bytes()
        for needle in needles:
            if needle.encode() in binary or needle.encode('utf-16-le') in binary:
                raise SystemExit('Private network value embedded in: ' + file.name)
        count += 1
print(json.dumps({'native_payload_files_present': True,
                  'private_network_values_not_embedded': True,
                  'binaries_scanned': count}))
