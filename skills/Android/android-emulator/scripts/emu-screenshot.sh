#!/usr/bin/env bash
# Save a PNG screenshot of the emulator and print its path.
# Usage: emu-screenshot.sh [out.png]   (default: /tmp/emu-screenshot-<timestamp>.png)
set -euo pipefail
source "$(dirname "$0")/_common.sh"
[[ "${1:-}" =~ ^(-h|--help)$ ]] && { sed -n '2,3p' "$0"; exit 0; }
out="${1:-/tmp/emu-screenshot-$(date +%Y%m%d-%H%M%S).png}"
require_device
mkdir -p "$(dirname "$out")"
tmp="$(mktemp "${out}.XXXX")"
trap 'rm -f "$tmp"' EXIT
adbs exec-out screencap -p >"$tmp"
# Validate PNG signature (guards against error text being saved as an image).
[[ "$(head -c 8 "$tmp" | od -An -tx1 | tr -d ' \n')" == 89504e470d0a1a0a ]] \
  || die "screencap did not return a PNG: $(head -c 200 "$tmp" | tr -d '\0')"
mv "$tmp" "$out"; trap - EXIT
echo "$out"
