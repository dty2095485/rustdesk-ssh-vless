#!/usr/bin/env python3
"""Refuse to publish release assets that carry private keys.

Run on every file before `gh release upload` / `gh release create`:

    python scripts/build/check_release_assets.py <file> [<file> ...]

Exit 0 only when every file is clean. A file fails when
  * its name looks like a server/Docker image (rustdesk-server-*, *.tar,
    *.tar.gz, *.tgz): hbssh embeds the SSH host private key at build time
    (build-hbssh-keys.sh), so server images never go to GitHub; or
  * it contains a private key marker anywhere, including inside nested tar /
    tar.gz archives (Docker image layers): PEM "BEGIN ... PRIVATE KEY", an
    OpenSSH key blob ("openssh-key-v1\\0"), or its base64 form.

Only paths and marker kinds are printed, never key material.
"""
from __future__ import annotations

import gzip
import io
import re
import sys
import tarfile
from pathlib import Path

BLOCKED_NAME = re.compile(r"(rustdesk-server|server-combined|\.tar(\.gz)?$|\.tgz$)", re.I)
MARKERS = [
    (re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"), "PEM private key"),
    (re.compile(rb"openssh-key-v1\x00"), "OpenSSH key blob"),
    (re.compile(rb"b3BlbnNzaC1rZXktdjE"), "base64 OpenSSH key"),
]
MAX_NESTING = 4
CHUNK = 8 << 20
OVERLAP = 128


def scan_stream(f, where: str, hits: list[str]) -> None:
    tail = b""
    seen = set()
    while True:
        block = f.read(CHUNK)
        if not block:
            break
        data = tail + block
        for rx, kind in MARKERS:
            if kind not in seen and rx.search(data):
                seen.add(kind)
                hits.append(f"{where}: {kind}")
        tail = data[-OVERLAP:]


def is_tar(head: bytes) -> bool:
    return len(head) >= 262 and head[257:262] == b"ustar"


def scan_bytes_source(open_fn, where: str, hits: list[str], depth: int) -> None:
    with open_fn() as f:
        head = f.read(512)
    if head[:2] == b"\x1f\x8b" and depth < MAX_NESTING:
        def gz_open():
            return gzip.open(open_fn())
        try:
            scan_bytes_source(gz_open, where + "!gunzip", hits, depth + 1)
            return
        except OSError:
            pass
    if is_tar(head) and depth < MAX_NESTING:
        with open_fn() as f, tarfile.open(fileobj=f, mode="r|*") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                data = tar.extractfile(member).read()
                scan_bytes_source(lambda d=data: io.BytesIO(d),
                                  f"{where}!{member.name}", hits, depth + 1)
        return
    with open_fn() as f:
        scan_stream(f, where, hits)


def check(path: Path) -> list[str]:
    problems = []
    if BLOCKED_NAME.search(path.name):
        problems.append(f"{path.name}: server/Docker image or tar archive; never upload these")
    hits: list[str] = []
    scan_bytes_source(lambda: open(path, "rb"), path.name, hits, 0)
    problems.extend(hits)
    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    failed = False
    for arg in argv:
        p = Path(arg)
        if not p.is_file():
            print(f"FAIL  {arg}: not a file")
            failed = True
            continue
        problems = check(p)
        if problems:
            failed = True
            print(f"FAIL  {p.name}")
            for x in problems:
                print(f"        {x}")
        else:
            print(f"ok    {p.name}")
    if failed:
        print("\nRefusing: remove the failing files from the upload.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
