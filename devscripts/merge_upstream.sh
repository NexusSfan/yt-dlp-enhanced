#!/bin/sh
# Integrate a reviewed upstream delta without advancing the baseline on failure.
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
git fetch upstream
new=$(git rev-parse --verify 'refs/remotes/upstream/master^{commit}')
if [ "$old" = "$new" ]; then
    echo 'Already synchronised'
    exit 0
fi
git merge-base --is-ancestor "$old" "$new"
patch=$(mktemp)
trap 'rm -f "$patch"' EXIT
trap 'exit 1' HUP INT TERM
git diff --binary --no-ext-diff --no-textconv "$old" "$new" > "$patch"
if [ ! -s "$patch" ]; then
    echo 'Empty upstream delta; review baseline advancement manually' >&2
    exit 1
fi
[ "$(git symbolic-ref --quiet HEAD)" = "$branch" ]
[ "$(git rev-parse --verify HEAD)" = "$original" ]
[ "$(git rev-parse --verify refs/tags/upstream-base)" = "$old_ref" ]
[ -z "$(git status --porcelain)" ]
git apply --index --check "$patch"
git apply --index "$patch"
[ "$(git symbolic-ref --quiet HEAD)" = "$branch" ]
[ "$(git rev-parse --verify HEAD)" = "$original" ]
git commit -m "Sync upstream $old..$new"
# Compare-and-swap: never overwrite another process's baseline.
git update-ref refs/tags/upstream-base "$new" "$old_ref"
