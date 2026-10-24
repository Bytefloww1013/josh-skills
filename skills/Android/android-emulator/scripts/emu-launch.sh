#!/usr/bin/env bash
# Launch an app by package (resolves its launcher activity) and wait until it has focus.
# Usage: emu-launch.sh <package> [activity] [--restart]
#   activity   e.g. .MainActivity or com.example/.MainActivity (optional)
#   --restart  clean start: force-stop the app and clear its task (am start -S, flags
#              NEW_TASK|CLEAR_TASK), so it opens on its main screen instead of resuming
# Exit: 0 launched and focused, 1 error, 3 launched but another window has focus
#       (dialog, permission prompt, or the app resumed into a sub-screen; try --restart)
set -euo pipefail
source "$(dirname "$0")/_common.sh"
pkg=""; act=""; restart=0
for a in "$@"; do
  case "$a" in
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    --restart) restart=1 ;;
    *) if [[ -z "$pkg" ]]; then pkg="$a"; else act="$a"; fi ;;
  esac
done
[[ -n "$pkg" ]] || { sed -n '2,8p' "$0" >&2; exit 2; }
require_device
adbs shell pm path "$pkg" 2>/dev/null | grep -q '^package:' \
  || die "package not installed: $pkg (list: adb shell pm list packages | grep -i <name>)"
start_opts=(-W)
if ((restart)); then
  adbs shell am force-stop "$pkg"
  start_opts+=(-S -f 0x10008000)   # FLAG_ACTIVITY_NEW_TASK | FLAG_ACTIVITY_CLEAR_TASK
fi
if [[ -n "$act" ]]; then
  [[ "$act" == */* ]] || act="$pkg/$act"
else
  act="$(adbs shell cmd package resolve-activity --brief -c android.intent.category.LAUNCHER "$pkg" 2>/dev/null | tr -d '\r' | tail -n1)"
fi
if [[ "$act" == */* ]]; then
  out="$(adbs shell am start "${start_opts[@]}" -n "$act" 2>&1 | tr -d '\r')"
  [[ "$out" == *Error* || "$out" == *Exception* ]] && die "am start failed: $out"
else
  adbs shell monkey -p "$pkg" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 \
    || die "no launcher activity for $pkg; pass one explicitly"
  act="(monkey)"
fi
for _ in $(seq 1 20); do
  focus="$(adbs shell dumpsys window 2>/dev/null | tr -d '\r' | grep -m1 -E 'mCurrentFocus=|mFocusedApp=' || true)"
  if [[ "$focus" == *"$pkg"* ]]; then echo "launched $act (focused)"; exit 0; fi
  sleep 0.5
done
echo "launched $act, but focus is: ${focus:-unknown}" >&2
echo "  (a dialog/permission prompt may be on top, or the app resumed a previous screen; try --restart)" >&2
exit 3
