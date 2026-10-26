#!/usr/bin/env bash
# Usage: guard-branch.sh <branch> <issue#> [base]
# Run before every commit and push: HEAD must be on <branch>, the issue's own branch, and never on the base branch.
b=$1; n=$2; base=$3; failed=0
[ -n "$b" ] && [ -n "$n" ] || { echo "FAIL: usage: guard-branch.sh <branch> <issue#> [base]"; exit 1; }
[ -n "$base" ] || base=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null); base=${base#origin/}; base=${base:-main}
cur=$(git branch --show-current)
if [ -z "$cur" ]; then echo "FAIL: HEAD is detached - check out $b"; failed=1
elif [ "$cur" = "$b" ]; then echo "PASS: on $b"; else echo "FAIL: on '$cur', not $b - switch back before committing"; failed=1; fi
if printf '%s' "$b" | grep -Eq "^[a-z]+/[a-z]+-issue$n-"; then echo "PASS: $b is issue #$n's branch"; else echo "FAIL: $b doesn't match */*-issue$n-*"; failed=1; fi
case "$b" in "$base" | main | master) echo "FAIL: $b is a base branch - never commit or push there"; failed=1 ;; *) echo "PASS: not the base branch ($base)" ;; esac
exit $failed
