#!/usr/bin/env bash
# Type text into the focused field (ASCII only), escaping spaces and shell metacharacters.
# Usage: emu-type.sh "text to type" [--enter] [--clear]
#   --clear  select-all + delete the field first   --enter  press ENTER afterwards
set -euo pipefail
source "$(dirname "$0")/_common.sh"
text=""; enter=0; clear=0; have=0
while (($#)); do
  case "$1" in
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    --enter) enter=1 ;;
    --clear) clear=1 ;;
    *) ((have)) && die "pass the text as ONE quoted argument"; text="$1"; have=1 ;;
  esac
  shift
done
((have)) || { sed -n '2,4p' "$0" >&2; exit 2; }
LC_ALL=C; [[ "$text" =~ ^[[:print:]]*$ ]] || die "only printable ASCII is supported by 'input text' (no emoji/accents/newlines; use --enter for Enter)"
require_device
if ((clear)); then
  adbs shell input keycombination KEYCODE_CTRL_LEFT KEYCODE_A >/dev/null 2>&1 || true
  adbs shell input keyevent KEYCODE_DEL
fi
# 'input text' runs through the device shell: backslash-escape every non-alphanumeric char,
# and encode spaces as %s (input's own space escape). Send in chunks; long strings get dropped.
esc=""
for (( i=0; i<${#text}; i++ )); do
  c="${text:i:1}"
  if [[ "$c" == " " ]]; then esc+="%s"
  elif [[ "$c" =~ [A-Za-z0-9] ]]; then esc+="$c"
  else esc+="\\$c"; fi
done
chunk=""; n=0
flush() { [[ -n "$chunk" ]] && adbs shell "input text $chunk"; chunk=""; n=0; }
i=0
while (( i < ${#esc} )); do
  if [[ "${esc:i:1}" == "\\" ]]; then tok="${esc:i:2}"; (( i+=2 ))
  elif [[ "${esc:i:2}" == "%s" ]]; then tok="%s"; (( i+=2 ))
  else tok="${esc:i:1}"; (( i+=1 )); fi
  chunk+="$tok"; (( n+=1 ))
  (( n >= 60 )) && flush
done
flush
((enter)) && adbs shell input keyevent KEYCODE_ENTER
echo "typed ${#text} chars$( ((enter)) && echo ' + ENTER')"
