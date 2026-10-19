#!/usr/bin/env bash
# Find an on-screen element by text, content-desc or resource-id and tap its center.
# Usage: emu-tap-text.sh "Text" [--exact] [--index N] [--wait SECONDS] [--dry-run]
#   --exact    no case-insensitive substring fallback
#   --index N  pick the Nth match (0-based) when several match
#   --wait S   keep re-dumping the UI up to S seconds until the element appears (default 0)
#   --dry-run  print the match and coordinates, don't tap
# Exit codes: 0 tapped/found, 1 not found, 2 usage error.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
query=""; exact=""; index=0; wait_s=0; dry=0
while (($#)); do
  case "$1" in
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    --exact) exact="--exact" ;;
    --index) index="${2:?--index needs N}"; shift ;;
    --wait) wait_s="${2:?--wait needs seconds}"; shift ;;
    --dry-run) dry=1 ;;
    *) [[ -z "$query" ]] || { echo "unexpected arg: $1" >&2; exit 2; }; query="$1" ;;
  esac
  shift
done
[[ -n "$query" ]] || { sed -n '2,8p' "$0" >&2; exit 2; }
require_device
xml="$(mktemp /tmp/emu-ui-XXXX.xml)"; trap 'rm -f "$xml"' EXIT
deadline=$(( SECONDS + wait_s ))
while :; do
  "$EMU_SCRIPTS_DIR/emu-ui-dump.sh" "$xml" >/dev/null
  if hit="$(python3 "$EMU_SCRIPTS_DIR/_ui.py" find "$xml" "$query" $exact --index "$index" 2>/tmp/emu-tap-err.$$)"; then
    rm -f /tmp/emu-tap-err.$$; break
  fi
  if (( SECONDS >= deadline )); then cat /tmp/emu-tap-err.$$ >&2; rm -f /tmp/emu-tap-err.$$; exit 1; fi
  sleep 1
done
read -r x y _ <<<"${hit%%$'\t'*}"
desc="${hit#*$'\t'}"
if (( dry )); then echo "found ($x,$y): $desc"; exit 0; fi
adbs shell input tap "$x" "$y"
echo "tapped ($x,$y): $desc"
