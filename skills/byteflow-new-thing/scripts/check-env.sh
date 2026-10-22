#!/usr/bin/env bash
# Reports OS and available shells/runtimes. Run from the project root.
case "$(uname -s)" in
  Darwin) os=macos ;;
  MINGW*|MSYS*|CYGWIN*) os=windows ;;
  *) os=linux ;;
esac
echo "INFO: os=$os bash=$BASH_VERSION"
for t in pwsh python python3 node; do
  if command -v "$t" >/dev/null 2>&1; then echo "INFO: $t=true"; else echo "INFO: $t=false"; fi
done
if [ "$os" = windows ]; then echo "INFO: script language=powershell (.ps1)"; else echo "INFO: script language=bash (.sh)"; fi

exit 0
