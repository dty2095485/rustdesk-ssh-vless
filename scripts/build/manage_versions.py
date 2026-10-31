"""Archive client releases separately from private network profiles."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone

DEFAULT_ROOT = Path('D:/RD/releases')
VERSION_RE = re.compile(r'^\d+\.\d+\.\d+\.\d+$')


def entries(root):
    result = []
    for path in root.iterdir():
        manifest = path / 'manifest.json'
        if VERSION_RE.fullmatch(path.name) and path.is_dir() and not path.is_symlink() and manifest.is_file():
            data = json.loads(manifest.read_text(encoding='utf-8'))
            if data.get('managed_by') == 'rustdesk-version-manager':
                result.append((path, data))
    return sorted(result, key=lambda item: tuple(map(int, item[0].name.split('.'))))


def next_version(root, upstream):
    if not re.fullmatch(r'\d+\.\d+\.\d+', upstream):
        raise ValueError('Expected official major.minor.patch version')
    suffixes = [int(p.name.rsplit('.', 1)[1]) for p, _ in entries(root) if p.name.startswith(upstream + '.')]
    return upstream + '.' + str(max(suffixes, default=0) + 1)


def register(root, version, artifact, platform, internal_version, note, build_code=0):
    if not VERSION_RE.fullmatch(version):
        raise ValueError('Expected official major.minor.patch.custom version')
    if not (artifact.name.lower().endswith(('.apk', '.exe', '.zip', '.msi', '.tar', '.tar.gz', '.tgz'))):
        raise ValueError('Only installation packages can be archived; never profile JSON')
    artifact = artifact.resolve(strict=True)
    folder = root / version
    manifest = folder / 'manifest.json'
    data = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {
        'managed_by': 'rustdesk-version-manager', 'version': version,
        'official_version': version.rsplit('.', 1)[0], 'custom_revision': int(version.rsplit('.', 1)[1]),
        'created_at': datetime.now(timezone.utc).isoformat(), 'artifacts': {},
    }
    if data.get('managed_by') != 'rustdesk-version-manager':
        raise ValueError('Refusing to overwrite unmanaged release')
    if platform in data['artifacts']:
        raise ValueError('This version/platform is immutable; allocate another revision')
    target_dir = folder / platform
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / artifact.name
    shutil.copy2(artifact, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    data['artifacts'][platform] = {'file': str(target.relative_to(folder)), 'sha256': digest,
        'internal_version': internal_version, 'build_code': build_code, 'note': note}
    temp = folder / 'manifest.json.tmp'
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(manifest)
    removed = []
    for old, _ in entries(root)[:-10]:
        resolved = old.resolve()
        if resolved.parent != root.resolve() or old.is_symlink() or old.is_junction():
            raise ValueError('Unsafe retention target: ' + str(old))
        shutil.rmtree(resolved)
        removed.append(old.name)
    catalog = {'keep_max': 10, 'versions': [data for _, data in entries(root)]}
    (root / 'versions-index.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'version': version, 'artifact': str(target), 'sha256': digest, 'removed_versions': removed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['next', 'register'])
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--upstream')
    parser.add_argument('--version')
    parser.add_argument('--artifact', type=Path)
    parser.add_argument('--platform', choices=['android', 'windows', 'docker', 'server'], default='android')
    parser.add_argument('--internal-version', default='unknown')
    parser.add_argument('--build-code', type=int, default=0)
    parser.add_argument('--note', default='')
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    if args.command == 'next':
        print(next_version(args.root, args.upstream))
    else:
        print(json.dumps(register(args.root, args.version, args.artifact, args.platform,
            args.internal_version, args.note, args.build_code), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
