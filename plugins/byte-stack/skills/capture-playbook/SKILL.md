---
name: capture-playbook
description: Capture a verified repo-specific workflow into .byte-stack/ using the deterministic Byte Stack scaffolder.
disable-model-invocation: true
argument-hint: "[key] [--update]"
---

# Capture playbook

Capture a proven workflow from the current session into the target Git worktree's `.byte-stack/` directory.

1. Locate the installed `bmode` skill directory (sibling `../bmode` in a full plugin install). If `bmode` is unavailable in a selective install, report that `bmode` is required and stop without writing unvalidated boilerplate manually.
2. From the target checkout, resolve the capture guide (`python3 "<bmode directory>/scripts/assets.py" resolve references capture-playbook.md`) and inspect the payload schema (`python3 "<bmode directory>/scripts/capture_playbook.py" schema`).
3. Extract the verified procedure into a JSON payload matching the schema (honoring any supplied `key`; exclude secrets and machine-local paths).
4. Run `python3 "<bmode directory>/scripts/capture_playbook.py" write --stdin --dry-run` first and show the unified diff (or exit `3` conflict details).
5. Write only after user confirmation (passing `--update` only for a confirmed clean managed update, and never `--force` without explicit approval), then verify with `capture_playbook.py validate` and `assets.py resolve`.
