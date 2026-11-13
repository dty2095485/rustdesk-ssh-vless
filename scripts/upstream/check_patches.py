#!/usr/bin/env python3
"""Check that every fork patch survived an upstream sync.

Reads patch-markers.txt (next to this script) and looks for each marker string
in the client tree. Two ways to point at the tree:

  check_patches.py --dir D:/RD/github-release/client
      a checked-out client tree (hbb_common vendored under libs/hbb_common)

  check_patches.py --mirror D:/RD/work/rustdesk-ssh/rustdesk --rev patches/1.5.3
                   [--hbb-rev patches/1.5.3]
      read straight from git objects, no checkout needed; libs/hbb_common/...
      paths are read from the hbb_common submodule repository at --hbb-rev
      (defaults to --rev)

Exit status 0 when every feature passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

HBB_PREFIX = "libs/hbb_common/"


def load_markers(path: Path):
    markers = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|", 2)]
        if len(parts) != 3 or not all(parts):
            sys.exit(f"{path}:{lineno}: expected '<feature> | <path> | <string>'")
        markers.append((lineno, *parts))
    return markers


class DirReader:
    def __init__(self, root: Path):
        self.root = root

    def read(self, rel: str):
        p = self.root / rel
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None


class GitReader:
    def __init__(self, repo: Path, rev: str, hbb_rev: str):
        self.repo, self.rev, self.hbb_rev = repo, rev, hbb_rev
        self.cache: dict[str, str | None] = {}

    def _show(self, repo: Path, spec: str):
        r = subprocess.run(["git", "-C", str(repo), "show", spec], capture_output=True)
        return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None

    def read(self, rel: str):
        if rel not in self.cache:
            if rel.startswith(HBB_PREFIX):
                hbb = self.repo / "libs" / "hbb_common"
                self.cache[rel] = self._show(hbb, f"{self.hbb_rev}:{rel[len(HBB_PREFIX):]}")
            else:
                self.cache[rel] = self._show(self.repo, f"{self.rev}:{rel}")
        return self.cache[rel]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--dir", type=Path, help="checked-out client tree")
    src.add_argument("--mirror", type=Path, help="upstream mirror repository")
    ap.add_argument("--rev", help="client revision in --mirror")
    ap.add_argument("--hbb-rev", help="hbb_common revision (default: --rev)")
    ap.add_argument("--markers", type=Path, default=Path(__file__).with_name("patch-markers.txt"))
    args = ap.parse_args()

    if args.mirror:
        if not args.rev:
            ap.error("--mirror needs --rev")
        reader = GitReader(args.mirror, args.rev, args.hbb_rev or args.rev)
    else:
        reader = DirReader(args.dir)

    features: "OrderedDict[str, list[str]]" = OrderedDict()
    for lineno, feature, rel, needle in load_markers(args.markers):
        problems = features.setdefault(feature, [])
        text = reader.read(rel)
        if text is None:
            problems.append(f"line {lineno}: file missing: {rel}")
        elif needle not in text.replace("\r\n", "\n"):
            problems.append(f"line {lineno}: not found in {rel}: {needle}")

    failed = 0
    for feature, problems in features.items():
        if problems:
            failed += 1
            print(f"FAIL  {feature}")
            for p in problems:
                print(f"        {p}")
        else:
            print(f"ok    {feature}")
    print(f"\n{len(features) - failed}/{len(features)} features present")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
