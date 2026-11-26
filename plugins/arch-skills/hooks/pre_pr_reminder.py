#!/usr/bin/env python3
"""PreToolUse hook: when the agent is about to run `gh pr create`, add a
reminder to run pr-erosion-check first. It never blocks the command.

Supports both Antigravity (`toolCall` / `hookEventName`) and Claude Code
(`tool_input`) payloads, answering each in its own response format.

The reminder is left out when every file the branch changes against the PR's
base is a doc file (DOC_EXTENSIONS). The repo is the last `cd <dir>` that
starts a command in the command line, else the hook's cwd (or first
workspacePath on Antigravity); the base is `--base`/`-B`, else origin's
default branch (origin/HEAD). If git can't answer, or the default branch is
not known, the reminder is shown.

Reads the hook JSON on stdin; prints one JSON object (or nothing on Claude Code
when no reminder applies)."""
import json
import os
import re
import shlex
import subprocess
import sys

PR_CREATE = re.compile(r"\bgh\s+pr\s+create\b")
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


def shell_words(cmd):
    """The command line as words, with `;`, `&&`, `||`, `|` and brackets as words of their own."""
    lexer = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return cmd.split()


def parse(cmd, cwd):
    """Returns (repo dir, base branch or None) from the shell command."""
    words = shell_words(cmd)
    repo, base = cwd, None
    starts_command = True
    for i, word in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else None
        if word and not word.strip("();<>|&"):
            starts_command = True
            continue
        if starts_command and word == "cd" and nxt:
            path = os.path.expanduser(nxt)
            repo = path if os.path.isabs(path) else os.path.join(repo, path)
        elif word in ("--base", "-B") and nxt:
            base = nxt
        elif word.startswith("--base="):
            base = word.split("=", 1)[1]
        starts_command = False
    return repo, base


def changed_files(repo, base):
    if base is None:
        base = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").split("/", 1)[1]
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
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError, IndexError):
        return False
    return bool(files) and all(os.path.splitext(f)[1].lower() in DOC_EXTENSIONS for f in files)


def extract_request(data):
    """Returns (is_antigravity, cmd, cwd) from a Claude Code or Antigravity hook payload."""
    is_antigravity = "toolCall" in data or "hookEventName" in data
    if is_antigravity:
        tool_call = data.get("toolCall")
        args = tool_call.get("args") if isinstance(tool_call, dict) else None
        args = args if isinstance(args, dict) else {}
        cmd = str(args.get("CommandLine") or args.get("command") or "")
        workspaces = data.get("workspacePaths")
        first_ws = workspaces[0] if isinstance(workspaces, list) and workspaces else ""
        cwd = str(args.get("Cwd") or data.get("cwd") or first_ws or os.getcwd())
        return True, cmd, cwd
    tool_input = data.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    cmd = str(tool_input.get("command") or "")
    cwd = str(data.get("cwd") or os.getcwd())
    return False, cmd, cwd


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    if not isinstance(data, dict):
        return
    is_antigravity, cmd, cwd = extract_request(data)
    remind = bool(PR_CREATE.search(cmd)) and not docs_only(cmd, cwd)
    if is_antigravity:
        out = {"decision": "allow"}
        if remind:
            out["reason"] = REMINDER
        print(json.dumps(out))
        return
    if not remind:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": REMINDER,
    }}))


if __name__ == "__main__":
    main()
