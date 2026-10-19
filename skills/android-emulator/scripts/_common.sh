#!/usr/bin/env bash
# Shared helpers for the emu-*.sh scripts. Source it; don't run it.
# Env overrides: ANDROID_HOME / ANDROID_SDK_ROOT, ADB (path to adb), ADB_SERIAL.

ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}}"
ADB_SERIAL="${ADB_SERIAL:-emulator-5554}"
# shellcheck disable=SC2034  # used by the scripts that source this file
EMU_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${ADB:-}" && -x "${ADB}" ]]; then
  ADB_BIN="$ADB"
elif [[ -x "$ANDROID_HOME/platform-tools/adb" ]]; then
  ADB_BIN="$ANDROID_HOME/platform-tools/adb"
elif command -v adb >/dev/null 2>&1; then
  ADB_BIN="$(command -v adb)"
else
  echo "error: adb not found (looked in \$ADB, $ANDROID_HOME/platform-tools, PATH)" >&2
  exit 127
fi

die() { echo "error: $*" >&2; exit 1; }

# adb against the selected device; stdin always /dev/null so adb never eats the caller's stdin.
adbs() { "$ADB_BIN" -s "$ADB_SERIAL" "$@" </dev/null; }

# Fail fast with a helpful message unless the device is online.
require_device() {
  local state
  state="$("$ADB_BIN" -s "$ADB_SERIAL" get-state </dev/null 2>&1 || true)"
  case "$state" in
    device) return 0 ;;
    *offline*) die "$ADB_SERIAL is offline. Try: $ADB_BIN kill-server && $ADB_BIN start-server" ;;
    *unauthorized*) die "$ADB_SERIAL is unauthorized. Try: $ADB_BIN kill-server; then restart the emulator (~/emulator-restart.sh)" ;;
    *) die "$ADB_SERIAL not connected ($state). Start it: ~/emulator-start.sh ; status: ~/emulator-status.sh" ;;
  esac
}
