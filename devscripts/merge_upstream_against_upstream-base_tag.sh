#!/bin/sh

git fetch upstream
git diff --binary upstream-base..upstream/master | git apply --index
git commit -m "Sync upstream $(git rev-parse --short upstream-base)..$(git rev-parse --short upstream/master)"
git tag -f upstream-base upstream/master
