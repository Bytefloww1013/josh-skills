#!/usr/bin/env bash
# External verification of the byte-stack performance scan (issue #36): checks V1-V6 from tests/perf/README.md.
#
# Usage: bash tests/perf/verify_scan.sh [--calibration FILE]
#
# Every scan runs against a throwaway XDG_STATE_HOME, so your own baseline is never read or changed. The scan needs a
# calibration; the script copies FILE (default: $XDG_STATE_HOME/byte-stack-perf/calibration.json, or
# ~/.local/state/byte-stack-perf/calibration.json) into each throwaway state folder. Run `scan.py calibrate` first if
# you have none.
#
# It runs about 7 full scans (about 1h30) on a quiet host (see "A quiet host" in tests/perf/README.md). Prints one PASS/FAIL line per check and exits 0
# only if every check passes, 1 if any fails, 2 on a usage error.
set -u

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
scan=(python3 "$here/scan.py")

calibration=""
while [ $# -gt 0 ]; do
  case "$1" in
    --calibration) calibration="${2-}"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "verify_scan: unknown argument" >&2; exit 2 ;;
  esac
done
if [ -z "$calibration" ]; then
  calibration="${XDG_STATE_HOME:-$HOME/.local/state}/byte-stack-perf/calibration.json"
fi
if [ ! -f "$calibration" ]; then
  echo "verify_scan: calibration file not found; run 'python3 tests/perf/scan.py calibrate' or pass --calibration" >&2
  exit 2
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/byte-stack-verify.XXXXXX")"
trap 'rm -rf "$work"' EXIT
failures=0

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; failures=$((failures + 1)); }

# new_state NAME: a fresh state folder holding only the calibration; prints the XDG_STATE_HOME to use.
new_state() {
  local xdg="$work/$1"
  mkdir -p "$xdg/byte-stack-perf"
  cp "$calibration" "$xdg/byte-stack-perf/calibration.json"
  echo "$xdg"
}

# run_scan XDG ARGS...: run scan.py with that state folder; sets $rc.
run_scan() {
  local xdg="$1"; shift
  XDG_STATE_HOME="$xdg" "${scan[@]}" "$@" >"$work/last.out" 2>"$work/last.err"
  rc=$?
}

baseline_sha() { sha256sum "$1/byte-stack-perf/baseline.json" 2>/dev/null | cut -d' ' -f1; }

# report XDG EXPR: evaluate a Python expression over the newest run's report.json (bound to r); prints the result.
# In a run report, "regressed" and "raised" hold objects with a "category" key; "not_measured" holds names.
report() {
  python3 - "$1/byte-stack-perf/runs" "$2" <<'EOF'
import json, sys
from pathlib import Path
runs = sorted(p for p in Path(sys.argv[1]).iterdir() if (p / "report.json").is_file())
r = json.loads((runs[-1] / "report.json").read_text())
print(eval(sys.argv[2], {"r": r}))
EOF
}

no_temp_files() { ! ls -A "$1/byte-stack-perf" | rg -q '\.tmp$'; }

# A plugin tree from HEAD with a fixed 50 ms sleep as the first statement of init.py (only INIT should move).
delayed="$work/delayed"
mkdir -p "$delayed"
git -C "$repo" archive HEAD plugins/byte-stack | tar -x -C "$delayed"
delayed="$delayed/plugins/byte-stack"
init_py="$delayed/skills/init/scripts/init.py"
{ echo "import time; time.sleep(0.050)"; cat "$init_py"; } >"$init_py.new" && mv "$init_py.new" "$init_py"

# V1 repeatability: init, then two runs on the same commit change nothing.
s1="$(new_state v1)"
run_scan "$s1" init
if [ "$rc" -eq 0 ]; then pass "V1 init exits 0"; else fail "V1 init exits 0 (got $rc)"; fi
h0="$(baseline_sha "$s1")"
for i in 1 2; do
  run_scan "$s1" run
  [ "$rc" -eq 0 ] && pass "V1 run $i exits 0" || fail "V1 run $i exits 0 (got $rc)"
  [ "$(report "$s1" 'len(r["regressed"])')" = "0" ] && pass "V1 run $i has no regressions" || fail "V1 run $i has no regressions"
  [ "$(report "$s1" 'len(r["raised"])')" = "0" ] && pass "V1 run $i raises nothing" || fail "V1 run $i raises nothing"
  [ "$(baseline_sha "$s1")" = "$h0" ] && pass "V1 run $i leaves the baseline byte-identical" || fail "V1 run $i leaves the baseline byte-identical"
done

# V2 fault injection: the delayed tree flags exactly INIT.L, exits 1 and writes nothing.
run_scan "$s1" run --src "$delayed"
[ "$rc" -eq 1 ] && pass "V2 exits exactly 1" || fail "V2 exits exactly 1 (got $rc)"
[ "$(report "$s1" 'sorted(c["category"] for c in r["regressed"])')" = "['INIT.L']" ] && pass "V2 regressed set is exactly {INIT.L}" \
  || fail "V2 regressed set is exactly {INIT.L} (got $(report "$s1" 'sorted(c["category"] for c in r["regressed"])'))"
[ "$(baseline_sha "$s1")" = "$h0" ] && pass "V2 leaves the baseline byte-identical" || fail "V2 leaves the baseline byte-identical"
no_temp_files "$s1" && pass "V2 leaves no temporary file" || fail "V2 leaves no temporary file"

# V3 harness errors exit 2 and write nothing.
RU="$work/missing-ru" run_scan "$s1" run
[ "$rc" -eq 2 ] && pass "V3 missing ru exits 2" || fail "V3 missing ru exits 2 (got $rc)"
PERF_FINGERPRINT_OVERRIDE=another-host run_scan "$s1" run
[ "$rc" -eq 2 ] && pass "V3 other fingerprint exits 2" || fail "V3 other fingerprint exits 2 (got $rc)"
[ "$(baseline_sha "$s1")" = "$h0" ] && pass "V3 leaves the baseline byte-identical" || fail "V3 leaves the baseline byte-identical"

# V4 schema: the baseline validates; seven bad records are rejected.
schema="$here/baseline.schema.json"
check() { uvx --quiet check-jsonschema==0.29.4 --schemafile "$schema" "$1" >/dev/null 2>&1; }
if check "$s1/byte-stack-perf/baseline.json"; then pass "V4 baseline validates"; else fail "V4 baseline validates"; fi
python3 - "$s1/byte-stack-perf/baseline.json" "$work/bad" <<'EOF'
import copy, json, sys
from pathlib import Path
good = json.loads(Path(sys.argv[1]).read_text()); out = Path(sys.argv[2]); out.mkdir()
def bad(name, edit):
    rec = copy.deepcopy(good); edit(rec); (out / f"{name}.json").write_text(json.dumps(rec))
bad("history", lambda r: r.__setitem__("history", []))
bad("score-over-100", lambda r: r["categories"]["INIT"].__setitem__("L", 100.5))
bad("no-suite", lambda r: r["categories"].pop("SUITE"))
bad("suite-no-io", lambda r: r["categories"]["SUITE"].pop("IO"))
bad("extra-group", lambda r: r["categories"].__setitem__("FOO", dict(r["categories"]["INIT"])))
bad("short-commit", lambda r: r.__setitem__("commit", r["commit"][:7]))
bad("schema-v2", lambda r: r.__setitem__("schema_version", 2))
EOF
for f in "$work"/bad/*.json; do
  name="$(basename "$f" .json)"
  if check "$f"; then fail "V4 rejects $name"; else pass "V4 rejects $name"; fi
done

# V6 partial runs judge only what they measure (run before V5, against the V1 baseline).
run_scan "$s1" run --only INIT --src "$delayed"
[ "$rc" -eq 1 ] && pass "V6 --only INIT on the delayed tree exits 1" || fail "V6 --only INIT on the delayed tree exits 1 (got $rc)"
[ "$(report "$s1" 'sorted(c["category"] for c in r["regressed"])')" = "['INIT.L']" ] && pass "V6 --only INIT flags exactly INIT.L" || fail "V6 --only INIT flags exactly INIT.L"
run_scan "$s1" run --only ASSETS --src "$delayed"
[ "$rc" -eq 0 ] && pass "V6 --only ASSETS on the delayed tree exits 0" || fail "V6 --only ASSETS on the delayed tree exits 0 (got $rc)"
[ "$(report "$s1" 'all(c in r["not_measured"] for c in ("INIT.L","INIT.U","INIT.M","INIT.IO"))')" = "True" ] \
  && pass "V6 --only ASSETS reports INIT as not measured" || fail "V6 --only ASSETS reports INIT as not measured"
run_scan "$s1" run --only NOPE
[ "$rc" -eq 2 ] && pass "V6 unknown selector exits 2" || fail "V6 unknown selector exits 2 (got $rc)"
[ "$(baseline_sha "$s1")" = "$h0" ] && pass "V6 leaves the baseline byte-identical" || fail "V6 leaves the baseline byte-identical"

# V5 the overwrite fires: init on the delayed tree, then a partial run on the clean tree raises only INIT.L.
s5="$(new_state v5)"
run_scan "$s5" init --src "$delayed"
[ "$rc" -eq 0 ] && pass "V5 init on the delayed tree exits 0" || fail "V5 init on the delayed tree exits 0 (got $rc)"
cp "$s5/byte-stack-perf/baseline.json" "$work/v5-before.json"
run_scan "$s5" run --only INIT
[ "$rc" -eq 0 ] && pass "V5 clean run exits 0" || fail "V5 clean run exits 0 (got $rc)"
[ "$(report "$s5" 'any(c["category"] == "INIT.L" for c in r["raised"])')" = "True" ] && pass "V5 reports INIT.L raised" || fail "V5 reports INIT.L raised"
verdict="$(python3 - "$work/v5-before.json" "$s5/byte-stack-perf/baseline.json" "$s5/byte-stack-perf/calibration.json" <<'EOF'
import json, sys
before, after, cal = (json.load(open(p)) for p in sys.argv[1:4])
eps_l = cal["eps"]["INIT"]["L"]
problems = []
if not after["categories"]["INIT"]["L"] > before["categories"]["INIT"]["L"] + eps_l:
    problems.append("INIT.L did not rise by more than eps")
for group, metrics in before["categories"].items():
    for metric, value in metrics.items():
        if group != "INIT" and after["categories"][group][metric] != value:
            problems.append(f"{group}.{metric} changed")
        if after["categories"][group][metric] < value:
            problems.append(f"{group}.{metric} went down")
print("ok" if not problems else "; ".join(problems))
EOF
)"
[ "$verdict" = "ok" ] && pass "V5 only INIT moved, INIT.L rose by more than eps, nothing went down" || fail "V5 marks ($verdict)"
check "$s5/byte-stack-perf/baseline.json" && pass "V5 new baseline validates" || fail "V5 new baseline validates"

if [ "$failures" -eq 0 ]; then echo "ALL CHECKS PASSED"; exit 0; fi
echo "$failures CHECK(S) FAILED"; exit 1
