#!/usr/bin/env bash
# Definition of Done check. Contract: one PASS/FAIL line per check; exit 0 only if all pass.
failed=0; ran=0

check() { # check "<name>" <command...>
  local name=$1; shift; ran=$((ran+1))
  if "$@" >/dev/null 2>&1; then echo "PASS: $name"; else echo "FAIL: $name"; failed=$((failed+1)); fi
}

# Examples - replace with one check per scripted DoD item / checkable guardrail:
# check "tests pass"         npm test --silent
# check "template unchanged" git diff --quiet HEAD -- templates/base.html
# check "output file exists" test -f dist/report.json

[ "$ran" -eq 0 ] && { echo "FAIL: no checks defined"; failed=1; }
if [ "$failed" -gt 0 ]; then echo "RESULT: FAIL ($failed)"; exit 1; fi
echo "RESULT: PASS"; exit 0
