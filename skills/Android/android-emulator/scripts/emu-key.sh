#!/usr/bin/env bash
# Send one or more key events. Names may omit the KEYCODE_ prefix.
# Usage: emu-key.sh HOME | BACK | ENTER | APP_SWITCH | DEL | TAB | POWER | WAKEUP | MENU | ... [more keys]
set -euo pipefail
source "$(dirname "$0")/_common.sh"
if (( $# == 0 )); then sed -n '2,3p' "$0" >&2; exit 2; fi
[[ "$1" =~ ^(-h|--help)$ ]] && { sed -n '2,3p' "$0"; exit 0; }
require_device
keys=()
for k in "$@"; do
  k="${k^^}"; [[ "$k" =~ ^[0-9]+$ || "$k" == KEYCODE_* ]] || k="KEYCODE_$k"
  keys+=("$k")
done
adbs shell input keyevent "${keys[@]}"
echo "sent: ${keys[*]}"
