#!/bin/sh
# Apply a reviewed upstream delta without changing the branch or baseline until both are ready.
set -eu

root=$(git rev-parse --show-toplevel)
[ -n "$root" ]
cd "$root"
status=$(git status --porcelain)
if [ -n "$status" ]; then
    echo 'Refusing to sync a dirty worktree or index' >&2
    exit 1
fi
branch=$(git symbolic-ref --quiet HEAD)
if [ "$branch" != refs/heads/master ]; then
    echo 'Refusing upstream sync outside master' >&2
    exit 1
fi
original=$(git rev-parse --verify HEAD)
old_ref=$(git rev-parse --verify refs/tags/upstream-base)
old=$(git rev-parse --verify 'refs/tags/upstream-base^{commit}')
if ! git merge-base --is-ancestor "$old" "$original"; then
    echo 'Refusing to sync master unrelated to upstream-base' >&2
    exit 1
fi
git fetch upstream
new=$(git rev-parse --verify 'refs/remotes/upstream/master^{commit}')
if [ "$old" = "$new" ]; then
    echo 'Already synchronised'
    exit 0
fi
git merge-base --is-ancestor "$old" "$new"

tmp=$(mktemp -d)
worktree="$tmp/worktree"
cleanup() {
    if [ -e "$worktree/.git" ]; then
        git worktree remove --force "$worktree" || {
            echo "Temporary sync worktree retained at $worktree" >&2
            return
        }
    fi
    rm -rf "$tmp"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

git diff --binary --no-ext-diff --no-textconv "$old" "$new" > "$tmp/patch"
if [ ! -s "$tmp/patch" ]; then
    echo 'Empty upstream delta; review baseline advancement manually' >&2
    exit 1
fi
git worktree add --detach "$worktree" "$original"
git -C "$worktree" apply --index "$tmp/patch"
expected_tree=$(git -C "$worktree" write-tree)
git -C "$worktree" commit -m "Sync upstream $old..$new"
candidate=$(git -C "$worktree" rev-parse --verify HEAD)
[ "$(git -C "$worktree" rev-parse "$candidate^")" = "$original" ]
[ "$(git -C "$worktree" rev-parse "$candidate^{tree}")" = "$expected_tree" ]

[ "$(git symbolic-ref --quiet HEAD)" = "$branch" ]
[ "$(git rev-parse --verify HEAD)" = "$original" ]
[ "$(git rev-parse --verify refs/tags/upstream-base)" = "$old_ref" ]
status=$(git status --porcelain)
[ -z "$status" ]

# Move both refs in one checked transaction; a failed hook or ref update leaves
# the real index/worktree untouched. Exclusive operator access is still required.
printf 'start\nupdate %s %s %s\nupdate refs/tags/upstream-base %s %s\nprepare\ncommit\n' \
    "$branch" "$candidate" "$original" "$new" "$old_ref" | git update-ref --stdin

# Refs have committed together. Refresh the checkout without discarding local edits.
# If interrupted here, the exact two commits make recovery explicit.
echo "Refs updated together: $original -> $candidate"
if ! git read-tree -m -u "$original" "$candidate"; then
    echo "Refs updated but checkout refresh failed; inspect status before recovering from $original to $candidate" >&2
    exit 1
fi
