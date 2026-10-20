#!/usr/bin/env bash
# Reports OS/shells and whether hooks (which /goal needs) are disabled. Run from the project root.
case "$(uname -s)" in
  Darwin) os=macos; managed="/Library/Application Support/ClaudeCode/managed-settings.json" ;;
  MINGW*|MSYS*|CYGWIN*) os=windows; managed="/c/Program Files/ClaudeCode/managed-settings.json" ;;
  *) os=linux; managed="/etc/claude-code/managed-settings.json" ;;
esac
echo "INFO: os=$os bash=$BASH_VERSION"
for t in pwsh python python3 node; do
  if command -v "$t" >/dev/null 2>&1; then echo "INFO: $t=true"; else echo "INFO: $t=false"; fi
done
if [ "$os" = windows ]; then echo "INFO: script language=powershell (.ps1)"; else echo "INFO: script language=bash (.sh)"; fi

hits=""
for f in "$HOME/.claude/settings.json" ".claude/settings.json" ".claude/settings.local.json" "$managed"; do
  [ -f "$f" ] && grep -Eq '"(disableAllHooks|allowManagedHooksOnly)"[[:space:]]*:[[:space:]]*true' "$f" && hits="$hits $f"
done
if [ -n "$hits" ]; then echo "FAIL: hooks restricted in$hits - /goal unavailable"; exit 1; fi
echo "PASS: hooks not disabled - /goal available"
exit 0
