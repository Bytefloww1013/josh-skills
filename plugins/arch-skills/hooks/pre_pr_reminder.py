#!/usr/bin/env python3
"""PreToolUse hook: when the agent is about to run `gh pr create`, add a
reminder to run pr-erosion-check first. It never blocks the command.

The reminder is left out when every file the branch changes against the PR's
base is a doc file (DOC_EXTENSIONS). The repo is the last `cd <dir>` in the
command, else the hook's cwd; the base is `--base`/`-B`, else origin's
default branch. If git can't answer, the reminder is shown.

Reads the hook JSON on stdin; prints one JSON object or nothing."""
import json
import os
import shlex
import subprocess
import sys

DOC_EXTENSIONS = {".md", ".mdx", ".markdown", ".txt", ".rst", ".adoc"}

REMINDER = (
    "Before this PR is opened: if you have not run the arch-skills:pr-erosion-check skill on this "
    "branch in this session, run it now with the linked issue as the yardstick, fix Critical and "
    "High findings, and include its verdict in your report. If you already ran it, go on. "
    "Skip it for a PR that only changes docs or makes text-only edits to non-code files.")


def git(repo, *args):
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=5)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    return out.stdout.strip()


def parse(cmd, cwd):
    """Returns (repo dir, base branch or None) from the shell command."""
    try:
        words = shlex.split(cmd, posix=True)
    except ValueError:
        words = cmd.split()
    repo, base = cwd, None
    for i, word in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else None
        if word == "cd" and nxt:
            path = os.path.expanduser(nxt)
            repo = path if os.path.isabs(path) else os.path.join(repo, path)
        elif word in ("--base", "-B") and nxt:
            base = nxt
        elif word.startswith("--base="):
            base = word.split("=", 1)[1]
    return repo, base


def changed_files(repo, base):
    if base is None:
        try:
            base = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").split("/", 1)[1]
        except RuntimeError:
            base = "main"
    for ref in (f"origin/{base}", base):
        try:
            git(repo, "rev-parse", "--verify", "--quiet", ref)
        except RuntimeError:
            continue
        return [f for f in git(repo, "diff", "--no-renames", "--name-only", f"{ref}...HEAD").splitlines() if f]
    raise RuntimeError(f"no base ref {base}")


def docs_only(cmd, cwd):
    try:
        files = changed_files(*parse(cmd, cwd))
    except (RuntimeError, OSError, subprocess.SubprocessError, IndexError):
        return False
    return bool(files) and all(os.path.splitext(f)[1].lower() in DOC_EXTENSIONS for f in files)


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    cmd = str((data.get("tool_input") or {}).get("command", ""))
    if "gh pr create" not in cmd:
        return
    if docs_only(cmd, str(data.get("cwd") or os.getcwd())):
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": REMINDER,
    }}))


if __name__ == "__main__":
    main()
