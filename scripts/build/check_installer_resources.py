"""Fail if the installer lacks an icon, version info or its manifest.

Checks the PE resource directory of the packaged installer, so a build that
silently loses the icon resource (csc without /win32res or /win32icon) is caught
before the artifact is archived.
"""
import struct
import sys
from pathlib import Path

RT_NAMES = {1: 'CURSOR', 3: 'ICON', 4: 'MENU', 5: 'DIALOG', 6: 'STRING',
            12: 'GROUP_CURSOR', 14: 'GROUP_ICON', 16: 'VERSION', 24: 'MANIFEST'}
REQUIRED = {3, 14, 16, 24}


def resource_types(path: Path):
    data = path.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    if data[pe:pe + 4] != b'PE\0\0':
        raise SystemExit(f'{path.name}: not a PE file')
    opt = pe + 24
    magic = struct.unpack_from('<H', data, opt)[0]
    dd = opt + (112 if magic == 0x20b else 96)
    rsrc_rva, _ = struct.unpack_from('<II', data, dd + 2 * 8)
    if not rsrc_rva:
        return []
    nsec = struct.unpack_from('<H', data, pe + 6)[0]
    sec_off = opt + struct.unpack_from('<H', data, pe + 20)[0]
    offset = None
    for i in range(nsec):
        s = sec_off + i * 40
        vsize, vaddr, rawsize, rawptr = struct.unpack_from('<IIII', data, s + 8)
        if vaddr <= rsrc_rva < vaddr + max(vsize, rawsize):
            offset = rsrc_rva - vaddr + rawptr
            break
    if offset is None:
        return []
    named, ids = struct.unpack_from('<HH', data, offset + 12)
    result = []
    for i in range(named + ids):
        tid = struct.unpack_from('<I', data, offset + 16 + i * 8)[0]
        result.append(tid)
    return result


def main():
    failed = False
    for arg in sys.argv[1:]:
        path = Path(arg)
        types = resource_types(path)
        names = sorted(RT_NAMES.get(t, str(t)) for t in types)
        missing = [RT_NAMES[t] for t in sorted(REQUIRED) if t not in types]
        status = 'OK' if not missing else f'MISSING {", ".join(missing)}'
        print(f'{path.name}: {", ".join(names) or "(none)"}  -> {status}')
        failed = failed or bool(missing)
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
