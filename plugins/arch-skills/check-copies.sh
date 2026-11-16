#!/usr/bin/env bash
# Fails when two copies of a shared file differ. Each skill carries its own copy of the reference files and scripts it
# shares with other skills, so it works when installed alone; edit every copy of a file together.
# Usage: plugins/arch-skills/check-copies.sh   (from anywhere)
set -euo pipefail
cd "$(dirname "$0")/skills"
status=0
for name in $(find . -path '*/references/*' -o -path '*/scripts/*' -type f | xargs -n1 basename | sort | uniq -d); do
  copies=$(find . \( -path '*/references/*' -o -path '*/scripts/*' \) -type f -name "$name")
  if [ "$(sha256sum $copies | cut -d' ' -f1 | sort -u | wc -l)" != 1 ]; then
    echo "differs: $name in" $copies
    status=1
  fi
done
[ "$status" = 0 ] && echo "all shared copies match"
exit "$status"
