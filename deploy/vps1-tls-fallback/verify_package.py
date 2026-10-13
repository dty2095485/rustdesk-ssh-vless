"""Verify current installer payload and reject embedded private profiles."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(r'<workspace>\work\rustdesk-ssh')
REPO = ROOT / 'rustdesk'
PAYLOAD = REPO / 'build/installer/payload.zip'
PROFILES = Path(r'<workspace>\releases\windows\ssh')


def sensitive_values(value, prefix=''):
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        path = prefix + '.' + key
        if isinstance(item, dict):
            yield from sensitive_values(item, path)
        elif isinstance(item, str) and item and key in {
                'server', 'server_name', 'uuid', 'private_key', 'public_key',
                'password', 'key', 'reality_public_key', 'reality_short_id'}:
            if len(item) >= 8 and item not in {'server.example.com'}:
                yield path, item.encode('utf-8'), item.encode('utf-16-le')


def main():
    secrets = []
    for name in ('VPS1-network.json', 'VPS3-network.json'):
        secrets.extend(sensitive_values(json.loads((PROFILES / name).read_text(encoding='utf-8-sig')), name))
    required = {
        'rustdesk.exe': REPO / 'flutter/build/windows/x64/runner/Release/rustdesk.exe',
        'librustdesk.dll': REPO / 'target/release/librustdesk.dll',
        'xray.exe': REPO / 'build/installer/RustDesk-client/xray.exe',
    }
    result = {}
    with zipfile.ZipFile(PAYLOAD) as archive:
        entries = {entry.filename.replace('\\', '/'): entry for entry in archive.infolist() if not entry.is_dir()}
        if 'flutter_windows.dll' not in entries:
            raise RuntimeError('Flutter engine missing from payload')
        for name, source in required.items():
            data = archive.read(entries[name])
            digest = hashlib.sha256(data).hexdigest()
            if digest != hashlib.sha256(source.read_bytes()).hexdigest():
                raise RuntimeError('payload is stale: ' + name)
            result[name] = digest
        for name, entry in entries.items():
            if name.endswith(('.pem', '.toml')) or name in {'VPS1-network.json', 'VPS3-network.json'}:
                raise RuntimeError('private configuration file included: ' + name)
            data = archive.read(entry)
            for field, utf8, utf16 in secrets:
                if utf8 in data or utf16 in data:
                    raise RuntimeError('embedded private profile field {} in {}'.format(field, name))
    print(json.dumps({'pass': True, 'private_profiles_embedded': False, 'payload_files': len(entries),
                      'sha256': result, 'payload_zip_sha256': hashlib.sha256(PAYLOAD.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
