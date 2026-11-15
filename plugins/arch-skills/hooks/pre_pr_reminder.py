#!/usr/bin/env python3
"""PreToolUse hook: when the agent is about to run `gh pr create`, add a
reminder to run pr-erosion-check first. It never blocks the command.
Reads the hook JSON on stdin; prints one JSON object or nothing."""
import json
import sys

try:
    data = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
cmd = str((data.get("tool_input") or {}).get("command", ""))
if "gh pr create" not in cmd:
    sys.exit(0)
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": (
        "Before this PR is opened: if you have not run the arch-skills:pr-erosion-check skill on this "
        "branch in this session, run it now with the linked issue as the yardstick, fix Critical and "
        "High findings, and include its verdict in your report. If you already ran it, go on."),
}}))
