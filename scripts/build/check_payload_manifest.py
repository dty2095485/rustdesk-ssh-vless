"""Compare the assembled Windows payload against the canonical file list.

1.5.1.3 shipped 21 of 75 flutter assets because the publisher repository was
missing 118 binary files that client/.gitignore excludes on import. A packaging
run that silently loses files now fails here instead of producing an installer.

Usage:
    check_payload_manifest.py --payload <dir> [--manifest <file>]
    check_payload_manifest.py --payload <dir> --write      # refresh the list

The manifest is one relative path per line, sorted, LF newlines.
"""
import argparse
import sys
from pathlib import Path

DEFAULT_MANIFEST = Path(__file__).parent / 'payload-manifest.txt'


def collect(payload: Path) -> list[str]:
    files = [p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file()]
    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', required=True)
    parser.add_argument('--manifest', default=str(DEFAULT_MANIFEST))
    parser.add_argument('--write', action='store_true', help='rewrite the manifest from this payload')
    args = parser.parse_args()

    payload = Path(args.payload)
    if not payload.is_dir():
        print(f'payload directory not found: {payload}')
        return 2
    manifest_path = Path(args.manifest)
    actual = collect(payload)

    if args.write:
        manifest_path.write_text('\n'.join(actual) + '\n', encoding='utf-8', newline='\n')
        print(f'wrote {len(actual)} entries to {manifest_path}')
        return 0

    if not manifest_path.is_file():
        print(f'manifest missing: {manifest_path} (create it with --write after verifying a payload)')
        return 2
    expected = [line for line in manifest_path.read_text(encoding='utf-8').splitlines() if line.strip()]

    missing = [p for p in expected if p not in set(actual)]
    extra = [p for p in actual if p not in set(expected)]
    print(f'payload files: {len(actual)}, manifest entries: {len(expected)}')
    if missing:
        print(f'MISSING ({len(missing)}):')
        for path in missing[:20]:
            print(f'  - {path}')
    if extra:
        print(f'EXTRA ({len(extra)}):')
        for path in extra[:20]:
            print(f'  + {path}')
    if missing or extra:
        return 1
    print('payload matches the manifest')
    return 0


if __name__ == '__main__':
    sys.exit(main())
