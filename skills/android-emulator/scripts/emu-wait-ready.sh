#!/usr/bin/env bash
# Wait until the emulator is fully booted and usable (boot_completed, package manager up,
# screen awake & unlocked). Usage: emu-wait-ready.sh [timeout_seconds=180]
set -euo pipefail
source "$(dirname "$0")/_common.sh"
[[ "${1:-}" =~ ^(-h|--help)$ ]] && { sed -n '2,3p' "$0"; exit 0; }
timeout="${1:-180}"
[[ "$timeout" =~ ^[0-9]+$ ]] || die "timeout must be an integer (seconds)"
deadline=$(( SECONDS + timeout ))

until [[ "$("$ADB_BIN" -s "$ADB_SERIAL" get-state </dev/null 2>/dev/null || true)" == device ]]; do
  (( SECONDS >= deadline )) && die "$ADB_SERIAL did not come online within ${timeout}s (is it started? ~/emulator-status.sh)"
  sleep 2
done
until [[ "$(adbs shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == 1 ]]; do
  (( SECONDS >= deadline )) && die "boot not completed within ${timeout}s (journalctl --user -u android-emulator -n 50)"
  sleep 2
done
until adbs shell pm path android >/dev/null 2>&1; do
  (( SECONDS >= deadline )) && die "package manager not ready within ${timeout}s"
  sleep 2
done
adbs shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1 || true
adbs shell wm dismiss-keyguard >/dev/null 2>&1 || true
echo "ready: $ADB_SERIAL (API $(adbs shell getprop ro.build.version.sdk | tr -d '\r'))"
