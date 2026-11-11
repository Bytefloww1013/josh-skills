#!/usr/bin/env python3
"""Check the handoff guard on sample sessions: each model's notices at the points its own window gives, subagents ignored,
HANDOFF_AT=0 switching it off, the settings rank, and the pending block, a saved (gitignored) or committed handoff, KEEP
pruning, the update and the paste-back working.

Usage: python3 check-handoff-guard.py [HOOK]
  HOOK  the handoff-guard.py to run (default: the one beside this file), e.g. a project's .claude/hooks/handoff-guard.py copy

It runs the hook as Claude Code does (one event as JSON on stdin) in a throwaway HOME, git project and session ids, with user
settings shaped like the real ones (modelSettings: Sonnet 150000, Opus and Fable 335000; Haiku left out to reach the fallback),
so no live session's state or settings are read or changed. Prints one PASS/FAIL line per check; exits 0 only if all pass.
"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

if sys.argv[1:2] in (["-h"], ["--help"]):
    sys.exit(print(__doc__.strip()))
HOOK = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("handoff-guard.py")).resolve()
RESERVE = 33_000  # Claude Code autocompacts at window - min(maxOutputTokens, 20000) - 13000
FALLBACK = 200_000  # the window the guard assumes when no setting names the model
WINDOWS = {"claude-opus-5-5": 335_000, "claude-fable-5-2": 335_000, "claude-sonnet-5-5": 150_000, "claude-haiku-5-5": FALLBACK}
home = Path(tempfile.mkdtemp(prefix="handoff-check-"))
project = home / "project"
states = home / ".claude" / "handoff-state"
failed = 0


def check(label, ok, detail=""):
    global failed
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}: {label}" + ("" if ok else f" ({detail})"))


def points(window):
    autocompact = window - RESERVE
    return autocompact, autocompact - 35_000, autocompact - 6_000


def transcript(sid, model, tokens):
    path = home / f"{sid}.jsonl"
    lines = [{"type": "user", "message": {"role": "user", "content": "go on"}},
             {"type": "assistant", "message": {"model": model, "usage": {"input_tokens": 3, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": tokens - 1003, "output_tokens": 50}}}]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return str(path)


def run(event, sid, env=None, root=None, **fields):
    """Run the hook on one event in root (default: the sample project); return (its JSON output or None, stderr)."""
    root = root or project
    data = {"hook_event_name": event, "session_id": sid, "cwd": str(root), **fields}
    base = {k: v for k, v in os.environ.items() if not k.startswith("HANDOFF_")}
    out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(data), capture_output=True, text=True, timeout=30,
                         env={**base, "HOME": str(home), "CLAUDE_PROJECT_DIR": str(root), **(env or {})})
    return (json.loads(out.stdout) if out.stdout.strip() else None), out.stderr.strip()


def context(out):
    return ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")


def state(sid):
    f = states / f"{sid}.json"
    return json.loads(f.read_text()) if f.exists() else None


def required(out, tokens, autocompact):
    text = context(out)
    return text.startswith("HANDOFF REQUIRED") and f"context is {tokens} tokens" in text and f"autocompact runs at {autocompact}." in text and "byte-handoff skill" in text


project.mkdir(parents=True)
subprocess.run(["git", "init", "-q", str(project)], check=True)
(project / ".gitignore").write_text("handoff/\n")
(home / ".claude").mkdir()
(home / ".claude" / "settings.json").write_text(json.dumps({"modelSettings": {m: {"autoCompactWindow": w} for m, w in WINDOWS.items() if w != FALLBACK}}))
print(f"hook: {HOOK}\nhome: {home}")

# Each model: nothing 1 token short of its handoff point, then HANDOFF REQUIRED at it, with its own autocompact point.
for model, window in WINDOWS.items():
    autocompact, handoff_at, _ = points(window)
    sid = f"check-{model}"
    out, err = run("UserPromptSubmit", sid, transcript_path=transcript(sid, model, handoff_at - 1))
    check(f"{model}: no notice at {handoff_at - 1} tokens", out is None and state(sid) is None and not err, err or context(out))
    out, err = run("PostToolUse", sid, tool_name="Read", transcript_path=transcript(sid, model, handoff_at))
    s = state(sid) or {}
    check(f"{model}: HANDOFF REQUIRED at {handoff_at} (window {window}, autocompact {autocompact})",
          required(out, handoff_at, autocompact) and s.get("status") == "pending" and s.get("at") == handoff_at and not err, err or context(out) or s)

# A subagent's events carry an agent_id: never measured, never blocked.
opus_ac, opus_at, opus_up = points(WINDOWS["claude-opus-5-5"])
out, err = run("PostToolUse", "check-subagent", agent_id="a1", tool_name="Read", transcript_path=transcript("check-subagent", "claude-fable-5-2", 900_000))
check("subagent: no notice and no state past every point", out is None and state("check-subagent") is None and not err, err or context(out))
out, err = run("PreToolUse", "check-claude-opus-5-5", agent_id="a1", tool_name="Edit", tool_input={"file_path": str(project / "app.py")})
check("subagent: not blocked while the main thread's handoff is pending", out is None and not err, err or out)

# The overrides: HANDOFF_AT=0 switches the guard off; HANDOFF_AT and HANDOFF_WINDOW move the points.
out, err = run("UserPromptSubmit", "check-off", env={"HANDOFF_AT": "0"}, transcript_path=transcript("check-off", "claude-opus-5-5", 900_000))
check("HANDOFF_AT=0: no notice and no state", out is None and state("check-off") is None and not err, err or context(out))
out, err = run("UserPromptSubmit", "check-at", env={"HANDOFF_AT": "100000"}, transcript_path=transcript("check-at", "claude-sonnet-5-5", 100_000))
check("HANDOFF_AT=100000: HANDOFF REQUIRED at 100000 on Sonnet", required(out, 100_000, points(150_000)[0]) and not err, err or context(out))
ac, at, _ = points(400_000)
out, err = run("UserPromptSubmit", "check-window", env={"HANDOFF_WINDOW": "400000"}, transcript_path=transcript("check-window", "claude-haiku-5-5", at))
check(f"HANDOFF_WINDOW=400000: unnamed model's notice at {at}, autocompact {ac}", required(out, at, ac) and not err, err or context(out))

# Settings rank, as Claude Code merges them: in one file a modelSettings entry beats its top-level autoCompactWindow, and the
# project's local settings come before its .claude/settings.json, which comes before the user's.
(project / ".claude").mkdir()
(project / ".claude" / "settings.json").write_text(json.dumps({"autoCompactWindow": 300_000, "modelSettings": {"claude-sonnet-5-5": {"autoCompactWindow": 180_000}}}))
for label, model, window in (("project modelSettings 180000 beats its own top-level 300000 and the user's 150000", "claude-sonnet-5-5", 180_000),
                             ("project top-level 300000 beats the user's modelSettings 335000", "claude-fable-5-2", 300_000)):
    ac, at, _ = points(window)
    sid = f"check-rank-{model}"
    out, err = run("UserPromptSubmit", sid, transcript_path=transcript(sid, model, at))
    check(f"{label}: {model}'s notice at {at}", required(out, at, ac) and not err, err or context(out))
(project / ".claude" / "settings.local.json").write_text(json.dumps({"autoCompactWindow": 250_000}))
ac, at, _ = points(250_000)
out, err = run("UserPromptSubmit", "check-local", transcript_path=transcript("check-local", "claude-sonnet-5-5", at))
check(f"settings.local.json top-level 250000 beats the project's modelSettings: Sonnet's notice at {at}", required(out, at, ac) and not err, err or context(out))
shutil.rmtree(project / ".claude")

# Pending: other tools are denied, handoff work isn't; a saved handoff ends it and the oldest beyond KEEP (3) are pruned.
sid = "check-claude-opus-5-5"
out, _ = run("PreToolUse", sid, tool_name="Edit", tool_input={"file_path": str(project / "app.py")})
check("pending: an Edit outside handoff/ is denied", (out or {}).get("hookSpecificOutput", {}).get("permissionDecision") == "deny", out)
out, _ = run("PreToolUse", sid, tool_name="Bash", tool_input={"command": "git status && mkdir -p handoff"})
check("pending: handoff shell work is allowed", out is None, out)
handoffs = project / "handoff"
handoffs.mkdir()
for n in range(1, 4):
    old = handoffs / f"handoff-20260101-00000{n}.md"
    old.write_text("old\n")
    os.utime(old, (time.time() - 3600, time.time() - 3600))
new = handoffs / "handoff-20260102-000000.md"
new.write_text("# Handoff\n- Goal: the sample task\n")
out, err = run("PostToolUse", sid, tool_name="Write", tool_input={"file_path": str(new)})
s = state(sid) or {}
kept = sorted(p.name for p in handoffs.glob("handoff-*.md"))
check("saved: status done, handoff recorded, newest 3 kept",
      context(out).startswith("Handoff saved") and s.get("status") == "done" and s.get("handoff") == str(new) and len(kept) == 3 and new.name in kept and not err, err or (context(out), s, kept))

# Where handoff/ is committed: a commit touching it ends the pending state, and nothing is pruned.
repo = home / "committed"
subprocess.run(["git", "init", "-q", str(repo)], check=True)
author = {"GIT_AUTHOR_NAME": "check", "GIT_AUTHOR_EMAIL": "check@example.invalid", "GIT_COMMITTER_NAME": "check", "GIT_COMMITTER_EMAIL": "check@example.invalid"}
out, err = run("UserPromptSubmit", "check-committed", root=repo, transcript_path=transcript("check-committed", "claude-opus-5-5", opus_at))
pending = required(out, opus_at, opus_ac) and not err
(repo / "handoff").mkdir()
names = [f"handoff-20260101-00000{n}.md" for n in range(1, 5)]
for name in names:
    (repo / "handoff" / name).write_text("# Handoff\n")
for cmd in (["add", "handoff"], ["commit", "-q", "-m", "docs: handoff"]):
    subprocess.run(["git", "-C", str(repo), *cmd], check=True, env={**os.environ, "HOME": str(home), **author})
out, err = run("PostToolUse", "check-committed", root=repo, tool_name="Bash", tool_input={"command": "git commit"})
s = state("check-committed") or {}
kept = sorted(p.name for p in (repo / "handoff").glob("handoff-*.md"))
check("committed: a commit touching handoff/ ends it, newest recorded, nothing pruned",
      pending and context(out).startswith("Handoff committed") and s.get("status") == "done" and s.get("handoff") == str(repo / "handoff" / names[-1]) and kept == names and not err,
      err or (context(out), s, kept))

# Done and still not compacted at the update point: HANDOFF UPDATE REQUIRED, once.
out, err = run("PostToolUse", sid, tool_name="Read", transcript_path=transcript(sid, "claude-opus-5-5", opus_up - 1))
check(f"done: no update notice at {opus_up - 1}", out is None and not err, err or context(out))
out, err = run("PostToolUse", sid, env={"HANDOFF_UPDATE_AT": str(opus_up + 1000)}, tool_name="Read", transcript_path=transcript(sid, "claude-opus-5-5", opus_up))
check(f"HANDOFF_UPDATE_AT={opus_up + 1000}: no update notice at {opus_up}", out is None and not err, err or context(out))
out, err = run("PostToolUse", sid, tool_name="Read", transcript_path=transcript(sid, "claude-opus-5-5", opus_up))
check(f"done: HANDOFF UPDATE REQUIRED at {opus_up}", context(out).startswith("HANDOFF UPDATE REQUIRED") and f"(at {opus_ac})" in context(out) and (state(sid) or {}).get("updated") is True, err or context(out))

# The autocompact: SessionStart(compact) pastes the handoff back in and deletes the state, which re-arms the guard.
out, err = run("SessionStart", sid, source="compact")
check("compact: handoff pasted back as Previous context, state cleared",
      context(out).startswith("Previous context") and "the sample task" in context(out) and state(sid) is None and not err, err or context(out))

if not failed:
    shutil.rmtree(home)  # kept on a failure, to look at
print(f"RESULT: {'PASS' if not failed else f'FAIL ({failed} failed; files in {home})'}")
sys.exit(1 if failed else 0)
