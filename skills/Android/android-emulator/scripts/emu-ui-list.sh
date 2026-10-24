#!/usr/bin/env bash
# Print a compact list of on-screen elements: "cx,cy  text/desc/id class [clickable]".
# Usage: emu-ui-list.sh [--all] [dump.xml]   (dumps the live screen if no file is given)
set -euo pipefail
source "$(dirname "$0")/_common.sh"
all=""; file=""
for a in "$@"; do
  case "$a" in
    -h|--help) sed -n '2,3p' "$0"; exit 0 ;;
    --all) all="--all" ;;
    *) file="$a" ;;
  esac
done
if [[ -z "$file" ]]; then
  file="$(mktemp /tmp/emu-ui-XXXX.xml)"; trap 'rm -f "$file"' EXIT
  "$EMU_SCRIPTS_DIR/emu-ui-dump.sh" "$file" >/dev/null
fi
python3 "$EMU_SCRIPTS_DIR/_ui.py" list "$file" $all
