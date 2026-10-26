#!/usr/bin/env bash
# Usage: check-branch.sh <branch> <issue#>
# Format: <descriptor>/<action>-issue<N>-<description>, e.g. feature/build-issue30-docs-context-system
b=$1; n=$2; failed=0
[ -n "$b" ] && [ -n "$n" ] || { echo "FAIL: usage: check-branch.sh <branch> <issue#>"; exit 1; }
descriptors='feature|bug|refactor|doc|chore|test|ci'
actions='add|build|change|delete|fix|install|move|remove|rename|update|upgrade'
if printf '%s' "$b" | grep -Eq '^[a-z]+/[a-z]+-issue[0-9]+-[a-z0-9]+(-[a-z0-9]+){1,2}$'; then echo "PASS: format <descriptor>/<action>-issue<N>-<2-3 word description>"
else echo "FAIL: '$b' does not match <descriptor>/<action>-issue<N>-<2-3 lower-case kebab words>"; failed=1; fi
d=${b%%/*}; rest=${b#*/}; a=${rest%%-*}
if printf '%s' "$d" | grep -Eqx "$descriptors"; then echo "PASS: descriptor $d"; else echo "FAIL: '$d' is not a descriptor (${descriptors//|/, })"; failed=1; fi
if printf '%s' "$a" | grep -Eqx "$actions"; then echo "PASS: action $a"; else echo "FAIL: '$a' is not an action (${actions//|/, })"; failed=1; fi
if printf '%s' "$b" | grep -Eq -- "-issue$n-"; then echo "PASS: issue number $n"; else echo "FAIL: issue number is not $n"; failed=1; fi
if [ "${#b}" -le 60 ]; then echo "PASS: ${#b} chars (<= 60)"; else echo "WARN: ${#b} chars (> 60) - shorten the description"; fi
git check-ref-format --branch "$b" >/dev/null 2>&1 && echo "PASS: valid git ref" || { echo "FAIL: invalid git ref"; failed=1; }
git show-ref --verify --quiet "refs/heads/$b" && echo "WARN: local branch already exists - resume or pick another name"
git ls-remote --exit-code --heads origin "$b" >/dev/null 2>&1 && echo "WARN: remote branch already exists - resume or pick another name"
exit $failed
