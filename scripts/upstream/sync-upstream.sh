#!/usr/bin/env bash
# Move the fork onto a new upstream RustDesk tag by rebasing the patch series.
#
#   bash scripts/upstream/sync-upstream.sh <new-upstream-tag>
#
# Re-run the same command after resolving conflicts; finished steps are skipped.
#
# Steps
#   1. fetch the tag from upstream into the mirror (tags are force-updated;
#      the series base is a commit id from series.conf, never a tag name)
#   2. rebase the client series   (mirror)          onto the new tag
#   3. rebase the hbb_common series (mirror/libs/hbb_common) onto the
#      hbb_common commit the new tag points at (skipped if unchanged)
#   4. check_patches.py on the rebased series
#   5. export: new branch upstream/<tag> in the release repo, client/ replaced
#      by the series (hbb_common vendored), series.conf updated, committed
#      locally (nothing is pushed). NO_EXPORT=1 stops after step 4.
#
# rerere is switched on in both mirror repositories, so a conflict resolved
# once is replayed automatically on the next sync.
set -euo pipefail

NEW_TAG=${1:?usage: sync-upstream.sh <new-upstream-tag>}
HERE=$(cd "$(dirname "$0")" && pwd)
RELEASE=$(cd "$HERE/../.." && pwd)
MIRROR=${MIRROR:-/d/RD/work/rustdesk-ssh/rustdesk}
HBB=$MIRROR/libs/hbb_common
WTROOT=${WTROOT:-/d/RD/work/sync-$NEW_TAG}
NEW_SERIES=patches/$NEW_TAG
EXPORT_BRANCH=upstream/$NEW_TAG
# shellcheck source=series.conf
. "$HERE/series.conf"

say()  { printf '\n== %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
rebasing() { [ -d "$(git -C "$1" rev-parse --git-path rebase-merge)" ] || [ -d "$(git -C "$1" rev-parse --git-path rebase-apply)" ]; }

[ "$NEW_TAG" != "$UPSTREAM_TAG" ] || die "series is already on $NEW_TAG"

# ---- 0. drift: client/ commits in the release repo that are not in the series --
conf_commit=$(git -C "$RELEASE" log -1 --format=%H master -- scripts/upstream/series.conf)
[ -n "$conf_commit" ] || die "series.conf is not committed on master yet"
drift=$(git -C "$RELEASE" log --format='%h %s' "$conf_commit..master" -- client)
if [ -n "$drift" ] && [ -z "${IGNORE_DRIFT:-}" ]; then
  cat >&2 <<EOF

ERROR: client/ changed on master after the series was last exported:
$drift

Port them into the series first (in the mirror, on $SERIES), e.g.
  git -C "$RELEASE" format-patch --relative=client -o /tmp/port $conf_commit..master -- client ':!client/libs/hbb_common'
  git -C "$MIRROR" checkout $SERIES && git -C "$MIRROR" am -3 /tmp/port/*.patch
(hbb_common changes: same with --relative=client/libs/hbb_common, applied in $HBB)
then re-run. IGNORE_DRIFT=1 skips this check.
EOF
  exit 3
fi
for r in "$MIRROR" "$HBB"; do
  git -C "$r" config rerere.enabled true
  git -C "$r" config rerere.autoupdate true
done

# ---- 1. fetch ---------------------------------------------------------------
say "fetch upstream tag $NEW_TAG"
git -C "$MIRROR" fetch --force origin "refs/tags/$NEW_TAG:refs/tags/$NEW_TAG"
git -C "$MIRROR" fetch --force origin "refs/tags/$UPSTREAM_TAG:refs/tags/$UPSTREAM_TAG" || true
NEW=$(git -C "$MIRROR" rev-parse "$NEW_TAG^{commit}")
old_now=$(git -C "$MIRROR" rev-parse -q --verify "$UPSTREAM_TAG^{commit}" || true)
if [ -n "$old_now" ] && [ "$old_now" != "$CLIENT_BASE" ]; then
  echo "note: upstream tag $UPSTREAM_TAG now points at ${old_now:0:9}, the series was built on ${CLIENT_BASE:0:9};"
  echo "      the rebase uses the recorded base, which is what you want."
fi
git -C "$MIRROR" merge-base --is-ancestor "$CLIENT_BASE" "$NEW" ||
  echo "note: $NEW_TAG does not contain the old base (upstream branched); the rebase still works, check the result closely."
NEW_HBB=$(git -C "$MIRROR" ls-tree "$NEW" libs/hbb_common | awk '{print $3}')
[ -n "$NEW_HBB" ] || die "$NEW_TAG has no libs/hbb_common submodule entry"
echo "upstream $NEW_TAG = ${NEW:0:9}, hbb_common = ${NEW_HBB:0:9} (series hbb base ${HBB_BASE:0:9})"
mkdir -p "$WTROOT"

# ---- 2. client series -------------------------------------------------------
CWT=$WTROOT/client
if ! git -C "$MIRROR" rev-parse -q --verify "refs/heads/$NEW_SERIES" >/dev/null; then
  say "rebase client series $SERIES onto $NEW_TAG"
  git -C "$MIRROR" worktree add -b "$NEW_SERIES" "$CWT" "$SERIES"
  if ! git -C "$CWT" rebase --onto "$NEW" "$CLIENT_BASE"; then
    cat <<EOF

The client rebase stopped on a conflict. In $CWT:
  git status                     # files to resolve (rerere already applied known fixes)
  ...edit, keep BOTH the fork lines and the upstream lines...
  git add <files>; git rebase --continue
For "build: lock files" prefer regenerating (cargo update -p <crate>, flutter pub get).
Then run this script again with the same tag.
EOF
    exit 2
  fi
elif rebasing "$CWT"; then
  die "client rebase still in progress in $CWT; finish it (git rebase --continue) and re-run"
else
  echo "client series $NEW_SERIES already rebased"
fi
git -C "$MIRROR" merge-base --is-ancestor "$NEW" "$NEW_SERIES" || die "$NEW_SERIES is not based on $NEW_TAG"
[ -z "$(git -C "$MIRROR" diff --name-only "$NEW" "$NEW_SERIES" -- libs/hbb_common)" ] ||
  die "$NEW_SERIES changes the hbb_common pointer; hbb_common patches belong in the hbb_common series"

# ---- 3. hbb_common series ---------------------------------------------------
if ! git -C "$HBB" rev-parse -q --verify "refs/heads/$NEW_SERIES" >/dev/null; then
  git -C "$HBB" fetch origin
  git -C "$HBB" cat-file -e "$NEW_HBB^{commit}" || die "hbb_common $NEW_HBB not found after fetch"
  if [ "$NEW_HBB" = "$HBB_BASE" ]; then
    say "hbb_common unchanged upstream, reuse $SERIES"
    git -C "$HBB" branch "$NEW_SERIES" "$SERIES"
  else
    say "rebase hbb_common series onto ${NEW_HBB:0:9}"
    HWT=$WTROOT/hbb_common
    git -C "$HBB" worktree add -b "$NEW_SERIES" "$HWT" "$SERIES"
    if ! git -C "$HWT" rebase --onto "$NEW_HBB" "$HBB_BASE"; then
      echo; echo "hbb_common rebase stopped on a conflict in $HWT; resolve, git rebase --continue, re-run."
      exit 2
    fi
  fi
else
  rebasing "$WTROOT/hbb_common" 2>/dev/null && die "hbb_common rebase still in progress in $WTROOT/hbb_common"
  echo "hbb_common series $NEW_SERIES already present"
fi

# ---- 4. patch survival --------------------------------------------------------
say "patch survival check"
python "$HERE/check_patches.py" --mirror "$MIRROR" --rev "$NEW_SERIES" --hbb-rev "$NEW_SERIES" ||
  die "patches lost during the rebase; fix the series in $CWT (git commit --fixup / rebase -i) and re-run"

# ---- 5. export into the release repository ------------------------------------
if [ -n "${NO_EXPORT:-}" ]; then
  echo; echo "NO_EXPORT set: series $NEW_SERIES is ready in the mirror, export skipped."
  exit 0
fi
RWT=$WTROOT/release
if git -C "$RELEASE" rev-parse -q --verify "refs/heads/$EXPORT_BRANCH" >/dev/null; then
  echo; echo "release branch $EXPORT_BRANCH already exists; delete it to export again."
  exit 0
fi
say "export to $EXPORT_BRANCH in $RELEASE"
git -C "$RELEASE" worktree add -b "$EXPORT_BRANCH" "$RWT" master
git -C "$RWT" rm -r -q client
rm -rf "$RWT/client"; mkdir -p "$RWT/client"
# autocrlf off: the mirror may convert to CRLF on checkout/archive
git -C "$MIRROR" -c core.autocrlf=false archive "$NEW_SERIES" | tar -x -C "$RWT/client"
rm -rf "$RWT/client/libs/hbb_common"; mkdir -p "$RWT/client/libs/hbb_common"
git -C "$HBB" -c core.autocrlf=false archive "$NEW_SERIES" | tar -x -C "$RWT/client/libs/hbb_common"
NEW_SERIES_SHA=$(git -C "$MIRROR" rev-parse "$NEW_SERIES")
NEW_HBB_SERIES_SHA=$(git -C "$HBB" rev-parse "$NEW_SERIES")
cat > "$RWT/scripts/upstream/series.conf" <<EOF
# Current patch series. sync-upstream.sh reads this and rewrites it on export.
# Bases are commit ids, not tag names: upstream has moved tags after release
# (1.5.1: e1ca097 -> 23e5bb4), so a tag name alone is not a reliable base.
UPSTREAM_TAG=$NEW_TAG
CLIENT_BASE=$NEW
HBB_BASE=$NEW_HBB
SERIES=$NEW_SERIES
EOF
# -f: client/.gitignore ignores upstream assets (1.5.1.3 shipped without them)
git -C "$RWT" add -A -f client
# Windows checkouts drop the exec bit; restore upstream's 100755 entries
git -C "$MIRROR" ls-tree -r "$NEW_SERIES" | awk '$1=="100755"{print "client/"$4}' |
  git -C "$RWT" update-index --chmod=+x --stdin
git -C "$RWT" add scripts/upstream/series.conf
python "$HERE/check_patches.py" --dir "$RWT/client" >/dev/null || die "exported tree fails the patch check"
git -C "$RWT" commit -q -s -F - <<EOF
chore(upstream): move the fork onto RustDesk $NEW_TAG

Upstream $NEW_TAG ($NEW), hbb_common ${NEW_HBB}.
Client series $NEW_SERIES = $NEW_SERIES_SHA
hbb_common series $NEW_SERIES = $NEW_HBB_SERIES_SHA
EOF
say "done"
cat <<EOF
Release branch : $EXPORT_BRANCH  (worktree $RWT, not pushed)
  git -C "$RWT" show --stat HEAD | tail -5
Next: build checks in $RWT (cargo check, dart analyze, rdtest e2e), version bump,
then merge $EXPORT_BRANCH into master and tag per docs/CODE-MANAGEMENT.md.
EOF
