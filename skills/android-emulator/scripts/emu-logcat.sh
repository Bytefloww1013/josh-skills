#!/usr/bin/env bash
# Show recent logcat lines for one app (by its pid), plus crashes for it.
# Usage: emu-logcat.sh <package> [lines=200] [--follow] [--level V|D|I|W|E]
#   If the app isn't running, prints its entries from the crash buffer and lines mentioning it.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
pkg=""; lines=200; follow=0; level=V
while (($#)); do
  case "$1" in
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    --follow|-f) follow=1 ;;
    --level) level="${2:?--level needs V|D|I|W|E}"; shift ;;
    *) if [[ -z "$pkg" ]]; then pkg="$1"; elif [[ "$1" =~ ^[0-9]+$ ]]; then lines="$1"; else die "bad arg: $1"; fi ;;
  esac
  shift
done
[[ -n "$pkg" ]] || { sed -n '2,4p' "$0" >&2; exit 2; }
[[ "$level" =~ ^[VDIWEF]$ ]] || die "--level must be one of V D I W E F"
require_device
pid="$(adbs shell pidof -s "$pkg" 2>/dev/null | tr -d '\r' || true)"
if [[ -n "$pid" ]]; then
  echo "== $pkg pid $pid (last $lines lines, level >= $level)"
  if ((follow)); then
    exec "$ADB_BIN" -s "$ADB_SERIAL" logcat -b main,system,crash --pid="$pid" "*:$level" </dev/null
  fi
  # -t is applied per buffer, so bound the dump and trim to exactly N lines ourselves.
  adbs logcat -d -b main,system --pid="$pid" -t 5000 "*:$level" | tail -n "$lines"
else
  echo "== $pkg is not running; lines mentioning it (main/system, last $lines):"
  adbs logcat -d -b main,system -t 5000 "*:$level" | grep -F "$pkg" | tail -n "$lines" || echo "(none)"
fi
echo "== crash buffer entries for $pkg:"
adbs logcat -d -b crash | grep -F -A 30 "Process: $pkg" | tail -n "$lines" || echo "(none)"
