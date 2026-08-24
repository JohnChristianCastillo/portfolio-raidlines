#!/usr/bin/env bash
# Publish the snapshot to the orphan 'data' branch.
#
#   scripts/publish-data.sh
#
# The JSON is big and rewritten on every refresh, so committing it to main would
# grow that history permanently by the size of a full snapshot each time. Instead it
# lives on a branch with no shared history, force-pushed each run: the remote keeps
# exactly one copy, and main stays small.
#
# Done through a throwaway worktree so the branch switch never touches your checkout,
# and onto a uniquely named local branch that is pushed to 'data' by refspec. An
# earlier version checked out --orphan data directly, which works once and then fails
# forever after, because the local branch it creates outlives the worktree.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
DATA="$ROOT/frontend/public/data"
BRANCH="${1:-data}"
TEMP_BRANCH="publish-data-$$"

if [ ! -d "$DATA" ]; then
  echo "no snapshot at $DATA. Run backend/tools/snapshot.py first." >&2
  exit 1
fi

COUNT=$(find "$DATA" -name '*.json' | wc -l | tr -d ' ')
SIZE=$(du -sh "$DATA" | cut -f1)
echo "publishing $COUNT files ($SIZE) to the '$BRANCH' branch"

WORK="$(mktemp -d)"
cleanup() {
  git -C "$ROOT" worktree remove --force "$WORK" 2>/dev/null || true
  git -C "$ROOT" branch -D "$TEMP_BRANCH" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

git -C "$ROOT" worktree add --detach "$WORK" >/dev/null
cd "$WORK"
git checkout --orphan "$TEMP_BRANCH"
git rm -rf --quiet . >/dev/null 2>&1 || true

cp -r "$DATA" ./data
git add -A
git commit --quiet -m "snapshot $(date -u +%Y-%m-%dT%H:%M:%SZ): $COUNT boards"
git push --force origin "HEAD:refs/heads/$BRANCH"

PUSHED=$(git ls-tree -r --name-only HEAD | wc -l | tr -d ' ')
echo "pushed $PUSHED files. Cloudflare will pick it up on its next build."
