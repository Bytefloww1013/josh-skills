#!/usr/bin/env bash
# Usage: check-claudemd.sh [path=./CLAUDE.md] [maxLines=200]
path=${1:-./CLAUDE.md}; max=${2:-200}; failed=0
[ -f "$path" ] || { echo "FAIL: $path not found"; exit 1; }
echo "PASS: $path exists"

# "under 200 if possible" -> soft limit
n=$(wc -l < "$path" | tr -d ' ')
if [ "$n" -le "$max" ]; then echo "PASS: $n lines (<= $max)"; else echo "WARN: $n lines (> $max) - prune it"; fi

for s in "TOOLS AND COMMANDS" "WORKFLOWS" "GOTCHAS"; do
  if grep -Eiq "^#+[[:space:]]*$s([^[:alnum:]]|$)" "$path"; then echo "PASS: section '$s'"
  else echo "FAIL: section '$s' missing"; failed=1; fi
done
exit $failed
