"""Lay out release artifacts in the official rustdesk-<version>-<arch> naming.

Two operations:
  normalize   rename every managed 1.x artifact to the official pattern and
              resync manifest.json hashes/paths
  publish     archive the new artifacts into releases/<version>/ and rewrite
              versions-index.json in ascending numeric order

Run:  python assemble_release.py normalize
      python assemble_release.py publish --version 1.5.1.1 --windows X --android Y --docker Z
"""
import argparse
import os
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get('RD_RELEASES_ROOT', r'D:\RD\releases'))
KEEP_MAX = 20
VERSION_RE = None

# platform -> suffix used in the official asset name
PLATFORM_ARCH = {
    'windows': 'x86_64.exe',
    'android': 'aarch64.apk',
    'docker': 'x86_64.tar',
    'server': 'x86_64.tar',
}


def official_name(version: str, platform: str) -> str:
    arch = PLATFORM_ARCH[platform]
    if platform in ('docker', 'server'):
        return f'rustdesk-server-combined-{version}-{arch}'
    return f'rustdesk-{version}-{arch}'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def managed_versions():
    result = []
    for path in ROOT.iterdir():
        if not path.is_dir():
            continue
        manifest = path / 'manifest.json'
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            continue
        if data.get('managed_by') != 'rustdesk-version-manager':
            continue
        try:
            key = tuple(int(part) for part in path.name.split('.'))
        except ValueError:
            continue
        result.append((key, path, data))
    result.sort(key=lambda item: item[0])
    return result


def write_manifest(folder: Path, data: dict):
    data['artifacts'] = dict(sorted(data['artifacts'].items()))
    (folder / 'manifest.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_sums(folder: Path, data: dict):
    lines = []
    for platform in sorted(data['artifacts']):
        entry = data['artifacts'][platform]
        lines.append(f"{entry['sha256']}  {entry['file']}")
    (folder / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_index():
    versions = [data for _, _, data in managed_versions()]
    catalog = {'keep_max': KEEP_MAX, 'versions': versions}
    (ROOT / 'versions-index.json').write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return [entry['version'] for entry in versions]


def normalize():
    changed = []
    for _, folder, data in managed_versions():
        touched = False
        for platform, entry in list(data['artifacts'].items()):
            if platform not in PLATFORM_ARCH:
                continue
            current = folder / entry['file']
            if not current.is_file():
                continue
            target = folder / platform / official_name(data['version'], platform)
            if current != target:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(current), str(target))
                touched = True
            digest = sha256(target)
            if entry['file'] != str(target.relative_to(folder)) or entry['sha256'] != digest:
                entry['file'] = str(target.relative_to(folder))
                entry['sha256'] = digest
                touched = True
        if touched:
            write_manifest(folder, data)
            write_sums(folder, data)
            changed.append(data['version'])
    order = write_index()
    print(json.dumps({'renamed_versions': changed, 'index_order': order}, ensure_ascii=False, indent=2))


def publish(args):
    folder = ROOT / args.version
    data = {
        'managed_by': 'rustdesk-version-manager',
        'version': args.version,
        'official_version': args.version.rsplit('.', 1)[0],
        'custom_revision': int(args.version.rsplit('.', 1)[1]),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'artifacts': {},
    }
    manifest_path = folder / 'manifest.json'
    if manifest_path.is_file():
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
    for platform, source, internal, build_code, note in (
        ('windows', args.windows, args.windows_version, 0, args.windows_note),
        ('android', args.android, args.android_version, args.android_build_code, args.android_note),
        ('docker', args.docker, args.docker_version, 0, args.docker_note),
    ):
        if not source:
            continue
        source = Path(source)
        if not source.is_file():
            raise SystemExit(f'missing artifact: {source}')
        target = folder / platform / official_name(args.version, platform)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        data['artifacts'][platform] = {
            'file': str(target.relative_to(folder)),
            'sha256': sha256(target),
            'internal_version': internal or args.version,
            'build_code': build_code,
            'note': note or '',
        }
    write_manifest(folder, data)
    write_sums(folder, data)
    order = write_index()
    print(json.dumps({'version': args.version, 'folder': str(folder),
                      'artifacts': data['artifacts'], 'index_order': order},
                     ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['normalize', 'publish'])
    parser.add_argument('--version')
    parser.add_argument('--windows')
    parser.add_argument('--android')
    parser.add_argument('--docker')
    parser.add_argument('--windows-version')
    parser.add_argument('--android-version')
    parser.add_argument('--docker-version')
    parser.add_argument('--android-build-code', type=int, default=0)
    parser.add_argument('--windows-note', default='Windows x64 Flutter installer; TLS/REALITY/SSH; no private network defaults')
    parser.add_argument('--android-note', default='Android arm64-v8a APK; TLS/REALITY/SSH; no private network defaults')
    parser.add_argument('--docker-note', default='Docker image tar (amd64); hbbs/hbbr/hbvless/hbssh + 3x-ui')
    args = parser.parse_args()
    if args.command == 'normalize':
        normalize()
    else:
        if not args.version:
            raise SystemExit('--version is required for publish')
        publish(args)


if __name__ == '__main__':
    main()
