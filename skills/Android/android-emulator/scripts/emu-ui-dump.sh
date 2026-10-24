#!/usr/bin/env bash
# Dump the current UI hierarchy (uiautomator XML) and print the local path.
# Usage: emu-ui-dump.sh [out.xml]   (default: /tmp/emu-ui-<timestamp>.xml; "-" = stdout)
set -euo pipefail
source "$(dirname "$0")/_common.sh"
[[ "${1:-}" =~ ^(-h|--help)$ ]] && { sed -n '2,3p' "$0"; exit 0; }
out="${1:-/tmp/emu-ui-$(date +%Y%m%d-%H%M%S).xml}"
require_device
remote=/sdcard/emu-ui-dump.xml
xml=""
for attempt in 1 2 3 4; do
  msg="$(adbs shell uiautomator dump "$remote" 2>&1 | tr -d '\r' || true)"
  if [[ "$msg" == *"dumped to"* ]]; then
    xml="$(adbs exec-out cat "$remote")"
    [[ "$xml" == *"<hierarchy"* ]] && break
  fi
  # Typical transient failure: "could not get idle state" while animating.
  sleep $(( attempt ))
done
adbs shell rm -f "$remote" >/dev/null 2>&1 || true
[[ "$xml" == *"<hierarchy"* ]] || die "uiautomator dump failed: ${msg:-no output}. Disable animations (see SKILL.md) and retry."
if [[ "$out" == - ]]; then
  printf '%s\n' "$xml"
else
  mkdir -p "$(dirname "$out")"
  printf '%s\n' "$xml" >"$out"
  echo "$out"
fi
