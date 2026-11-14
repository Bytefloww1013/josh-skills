#!/usr/bin/env python3
"""Check the handoff guard on sample sessions: each model's notices at the points its own window gives, subagents ignored,
HANDOFF_AT=0 switching it off, the settings rank, and the pending block, a saved (gitignored) or committed handoff, KEEP
pruning and the paste-back working.

Also: handoffs from other sessions sharing handoff/ are never recorded, end the pending state or get pruned while live.

Usage: python3 check-handoff-guard.py [HOOK]
  HOOK  the handoff-guard.py to run (default: the one beside this file), e.g. a project's .claude/hooks/handoff-guard.py copy

It runs the hook as Claude Code does (one event as JSON on stdin) in a throwaway HOME, git project and session ids, with user
settings shaped like the real ones (modelSettings: Sonnet 150000, Opus and Fable 335000; Haiku and an unknown model are left out,
to get their model's own window),
so no live session's state or settings are read or changed. Prints one PASS/FAIL line per check; exits 0 only if all pass.
"""
import json, os, re, shutil, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

if sys.argv[1:2] in (["-h"], ["--help"]):
    sys.exit(print(__doc__.strip()))
HOOK = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("handoff-guard.py")).resolve()
RESERVE = 33_000  # Claude Code autocompacts at window - min(maxOutputTokens, 20000) - 13000
WINDOWS = {"claude-opus-5-5": 335_000, "claude-fable-5-2": 335_000, "claude-sonnet-5-5": 150_000}  # named by the sample user settings
DEFAULTS = {"claude-haiku-5-5": 1_000_000, "claude-haiku-4-5-20251001": 200_000, "claude-test-9": 200_000}  # left out: their model's own window
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
    return autocompact, autocompact - 35_000


def usage(tokens):
    return {"input_tokens": 3, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": tokens - 1053, "output_tokens": 50}


def reply(model, tokens, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain, "message": {"model": model, "usage": usage(tokens)}}


def advisor_reply(model, before, after, read):
    """A response that called the advisor, shaped like Claude Code 2.1.322's: the top-level fields add up both message
    iterations (before + after), the advisor's own read is a separate iteration."""
    its = [{**usage(before), "type": "message"}, {"input_tokens": read, "output_tokens": 9000, "type": "advisor_message", "model": "claude-fable-5-2"}, {**usage(after), "type": "message"}]
    total = {"input_tokens": 6, "cache_creation_input_tokens": 2000, "cache_read_input_tokens": before + after - 2006, "output_tokens": 100}
    return {"type": "assistant", "message": {"model": model, "usage": {**total, "iterations": its}}}


def boundary(pre):
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"type": "system", "subtype": "compact_boundary", "timestamp": stamp, "compactMetadata": {"trigger": "auto", "preTokens": pre}}


def write(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in [{"type": "user", "message": {"role": "user", "content": "go on"}}, *entries]))
    return str(path)


def transcript(sid, model, tokens, *more):
    return write(home / f"{sid}.jsonl", [reply(model, tokens), *more])


def run_raw(event, sid, env=None, root=None, **fields):
    """Run the hook on one event in root (default: the sample project); return (exit code, stdout, stderr)."""
    root = root or project
    data = {"hook_event_name": event, "session_id": sid, "cwd": str(root), **fields}
    drop = ("CLAUDE_CODE_AUTO_COMPACT_WINDOW", "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "CLAUDE_CODE_DISABLE_1M_CONTEXT",
            "CLAUDE_CODE_MAX_CONTEXT_TOKENS", "CLAUDE_CODE_MAX_OUTPUT_TOKENS")  # a developer's shell may hold these
    base = {k: v for k, v in os.environ.items() if not k.startswith("HANDOFF_") and k not in drop}
    out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(data), capture_output=True, text=True, timeout=30,
                         env={**base, "HOME": str(home), "CLAUDE_PROJECT_DIR": str(root), **(env or {})})
    return out.returncode, out.stdout, out.stderr.strip()


def run(event, sid, env=None, root=None, **fields):
    """run_raw for the events that answer in JSON; return (its JSON output or None, stderr)."""
    _, stdout, err = run_raw(event, sid, env, root, **fields)
    return (json.loads(stdout) if stdout.strip() else None), err


def context(out):
    return ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")


def state(sid):
    f = states / f"{sid}.json"
    return json.loads(f.read_text()) if f.exists() else None


def tag(sid):
    return "".join(c for c in sid if c.isalnum())[:8]


def required(out, tokens, autocompact):
    text = context(out)
    return text.startswith("HANDOFF REQUIRED") and f"context is {tokens} tokens" in text and f"autocompact runs at {autocompact}." in text and "byte-handoff skill" in text


project.mkdir(parents=True)
subprocess.run(["git", "init", "-q", str(project)], check=True)
(project / ".gitignore").write_text("handoff/\n")
(home / ".claude").mkdir()
(home / ".claude" / "settings.json").write_text(json.dumps({"modelSettings": {m: {"autoCompactWindow": w} for m, w in WINDOWS.items()}}))
print(f"hook: {HOOK}\nhome: {home}")

# Each model: nothing 1 token short of its handoff point, then HANDOFF REQUIRED at it, with its own autocompact point.
for model, window in {**WINDOWS, **DEFAULTS}.items():
    autocompact, handoff_at = points(window)
    sid = f"check-{model}"
    out, err = run("UserPromptSubmit", sid, transcript_path=transcript(sid, model, handoff_at - 1))
    check(f"{model}: no notice at {handoff_at - 1} tokens", out is None and state(sid) is None and not err, err or context(out))
    out, err = run("PostToolUse", sid, tool_name="Read", transcript_path=transcript(sid, model, handoff_at))
    s = state(sid) or {}
    check(f"{model}: HANDOFF REQUIRED at {handoff_at} (window {window}, autocompact {autocompact})",
          required(out, handoff_at, autocompact) and s.get("status") == "pending" and s.get("at") == handoff_at and not err, err or context(out) or s)

# A subagent's events carry an agent_id: never measured, never blocked.
opus_ac, opus_at = points(WINDOWS["claude-opus-5-5"])
out, err = run("PostToolUse", "check-subagent", agent_id="a1", tool_name="Read", transcript_path=transcript("check-subagent", "claude-fable-5-2", 900_000))
check("subagent: no notice and no state past every point", out is None and state("check-subagent") is None and not err, err or context(out))
out, err = run("PreToolUse", "check-claude-opus-5-5", agent_id="a1", tool_name="Edit", tool_input={"file_path": str(project / "app.py")})
check("subagent: not blocked while the main thread's handoff is pending", out is None and not err, err or out)

# The overrides: HANDOFF_AT=0 switches the guard off; HANDOFF_AT and HANDOFF_WINDOW move the points.
out, err = run("UserPromptSubmit", "check-off", env={"HANDOFF_AT": "0"}, transcript_path=transcript("check-off", "claude-opus-5-5", 900_000))
check("HANDOFF_AT=0: no notice and no state", out is None and state("check-off") is None and not err, err or context(out))
out, err = run("UserPromptSubmit", "check-at", env={"HANDOFF_AT": "100000"}, transcript_path=transcript("check-at", "claude-sonnet-5-5", 100_000))
check("HANDOFF_AT=100000: HANDOFF REQUIRED at 100000 on Sonnet", required(out, 100_000, points(150_000)[0]) and not err, err or context(out))
ac, at = points(400_000)
out, err = run("UserPromptSubmit", "check-window", env={"HANDOFF_WINDOW": "400000"}, transcript_path=transcript("check-window", "claude-test-9", at))
check(f"HANDOFF_WINDOW=400000: unknown model's notice at {at}, autocompact {ac}", required(out, at, ac) and not err, err or context(out))

# Settings rank, as Claude Code merges them: in one file a modelSettings entry beats its top-level autoCompactWindow, and the
# project's local settings come before its .claude/settings.json, which comes before the user's.
(project / ".claude").mkdir()
(project / ".claude" / "settings.json").write_text(json.dumps({"autoCompactWindow": 300_000, "modelSettings": {"claude-sonnet-5-5": {"autoCompactWindow": 180_000}}}))
for label, model, window in (("project modelSettings 180000 beats its own top-level 300000 and the user's 150000", "claude-sonnet-5-5", 180_000),
                             ("project top-level 300000 beats the user's modelSettings 335000", "claude-fable-5-2", 300_000)):
    ac, at = points(window)
    sid = f"check-rank-{model}"
    out, err = run("UserPromptSubmit", sid, transcript_path=transcript(sid, model, at))
    check(f"{label}: {model}'s notice at {at}", required(out, at, ac) and not err, err or context(out))
(project / ".claude" / "settings.local.json").write_text(json.dumps({"autoCompactWindow": 250_000}))
ac, at = points(250_000)
out, err = run("UserPromptSubmit", "check-local", transcript_path=transcript("check-local", "claude-sonnet-5-5", at))
check(f"settings.local.json top-level 250000 beats the project's modelSettings: Sonnet's notice at {at}", required(out, at, ac) and not err, err or context(out))
ac, at = points(200_000)
out, err = run("UserPromptSubmit", "check-rank-cap", transcript_path=transcript("check-rank-cap", "claude-haiku-4-5-20251001", at))
check(f"project top-level 300000 on claude-haiku-4-5-20251001: capped at the model's 200000, notice at {at}", required(out, at, ac) and not err, err or context(out))
shutil.rmtree(project / ".claude")

# Env vars and settings values Claude Code itself reads (CLAUDE_CODE_AUTO_COMPACT_WINDOW beats every setting).
ac, at = points(200_000)
out, err = run("UserPromptSubmit", "check-no1m", env={"CLAUDE_CODE_DISABLE_1M_CONTEXT": "1"}, transcript_path=transcript("check-no1m", "claude-haiku-5-5", at))
check(f"CLAUDE_CODE_DISABLE_1M_CONTEXT=1 on claude-haiku-5-5: notice at {at}", required(out, at, ac) and not err, err or context(out))
out, err = run("UserPromptSubmit", "check-envwin", env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "200k"}, transcript_path=transcript("check-envwin", "claude-opus-5-5", at))
check(f"CLAUDE_CODE_AUTO_COMPACT_WINDOW=200k beats the user's Opus 335000: notice at {at}", required(out, at, ac) and not err, err or context(out))
out, err = run("UserPromptSubmit", "check-pct", env={"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "50"}, transcript_path=transcript("check-pct", "claude-sonnet-5-5", 30_000))
check("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50 on Sonnet 150000: autocompact 65000, notice at 30000", required(out, 30_000, 65_000) and not err, err or context(out))
(project / ".claude").mkdir()
(project / ".claude" / "settings.json").write_text(json.dumps({"autoCompactWindow": "auto"}))
ac, at = points(1_000_000)
out, err = run("UserPromptSubmit", "check-auto", transcript_path=transcript("check-auto", "claude-opus-5-5", at))
check(f"autoCompactWindow \"auto\" in the project: Opus's own 1M beats the user's 335000, notice at {at}", required(out, at, ac) and not err, err or context(out))
(project / ".claude" / "settings.json").write_text(json.dumps({"modelSettings": {"claude-opus-5": {"autoCompactWindow": 150_000}}}))
out, err = run("UserPromptSubmit", "check-exactkey-low", transcript_path=transcript("check-exactkey-low", "claude-opus-5-5", points(150_000)[1]))
check("modelSettings key claude-opus-5 is not claude-opus-5-5: no notice at 82000", out is None and state("check-exactkey-low") is None and not err, err or context(out))
out, err = run("UserPromptSubmit", "check-exactkey", transcript_path=transcript("check-exactkey", "claude-opus-5-5", opus_at))
check(f"modelSettings key claude-opus-5 is not claude-opus-5-5: the user's 335000 applies, notice at {opus_at}", required(out, opus_at, opus_ac) and not err, err or context(out))
shutil.rmtree(project / ".claude")

# Output tokens count: a reply of 266000 read + 1000 created + 3 input + 1000 output is 267000.
entry = {"type": "assistant", "message": {"model": "claude-opus-5-5", "usage": {"input_tokens": 3, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 266_000 - 1003, "output_tokens": 1000}}}
out, err = run("UserPromptSubmit", "check-output", transcript_path=write(home / "check-output.jsonl", [entry]))
check("output tokens counted: 267000 on Opus gives HANDOFF REQUIRED", required(out, opus_at, opus_ac) and not err, err or context(out))

# The ceiling: the last auto compaction's preTokens lowers the autocompact point (here from 302000 to 150000).
out, err = run("UserPromptSubmit", "check-ceiling", transcript_path=transcript("check-ceiling", "claude-opus-5-5", 140_000, boundary(150_000), reply("claude-opus-5-5", 115_000)))
check("ceiling: a compaction at 150000 puts the notice at 115000, autocompact 150000", required(out, 115_000, 150_000) and not err, err or context(out))

# Root and path: Claude Code's project folder, not the cwd's own git root, holds handoff/, and the path is named once.
nested = project / "nested"
nested.mkdir()
subprocess.run(["git", "init", "-q", str(nested)], check=True)
nenv = {"CLAUDE_PROJECT_DIR": str(project)}
sid = "check-nested"
out, err = run("UserPromptSubmit", sid, root=nested, env=nenv, transcript_path=transcript(sid, "claude-opus-5-5", opus_at))
s = state(sid) or {}
pat = re.compile(re.escape(str(project / "handoff")) + r"/handoff-\d{8}-\d{6}-" + tag(sid) + r"\.md")
path = s.get("path", "")
check("nested repo: state path is <project>/handoff/handoff-<stamp>-<tag>.md and the notice names it", bool(pat.fullmatch(path)) and path in context(out) and not err, err or (path, context(out)))
out, err = run("PreToolUse", sid, root=nested, env=nenv, tool_name="Edit", tool_input={"file_path": str(project / "app.py")})
deny = ((out or {}).get("hookSpecificOutput") or {}).get("permissionDecision")
reason = ((out or {}).get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")
check("nested repo: an Edit is denied and the deny names the same path", deny == "deny" and path in reason and not err, err or out)
out, err = run("PreToolUse", sid, root=nested, env=nenv, tool_name="Write", tool_input={"file_path": path})
check("nested repo: a Write to that path is allowed", out is None and not err, err or out)

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
names = [f"handoff-20260101-00000{n}.md" for n in range(1, 4)] + [f"handoff-20260101-000000-{tag('check-committed')}.md"]


def commit(*files):
    for f in files:
        (repo / "handoff" / f).write_text("# Handoff\n")
    for cmd in (["add", "handoff"], ["commit", "-q", "-m", "docs: handoff"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, env={**os.environ, "HOME": str(home), **author})


commit(*names[:3])  # other sessions' handoffs, committed while this one is pending
out, err = run("PostToolUse", "check-committed", root=repo, tool_name="Bash", tool_input={"command": "git commit"})
check("committed: another session's handoff commit leaves this one pending", out is None and (state("check-committed") or {}).get("status") == "pending" and not err, err or context(out))
commit(names[3])
out, err = run("PostToolUse", "check-committed", root=repo, tool_name="Bash", tool_input={"command": "git commit"})
s = state("check-committed") or {}
kept = sorted(p.name for p in (repo / "handoff").glob("handoff-*.md"))
check("committed: this session's tagged commit ends it, its own file recorded (not the newest name), nothing pruned",
      pending and context(out).startswith("Handoff committed") and s.get("status") == "done" and s.get("handoff") == str(repo / "handoff" / names[3]) and kept == sorted(names) and not err,
      err or (context(out), s, kept))

# The main thread's autocompact with its handoff saved: PreCompact lets it run, tells the summarizer to continue from the handoff
# and leaves a marker; SessionStart(compact) goes by the marker: it deletes the state (re-arming the guard) and pastes the handoff.
code, out, err = run_raw("PreCompact", sid, trigger="auto", transcript_path=transcript(sid, "claude-opus-5-5", opus_ac))
check("main compact: PreCompact with a saved handoff lets it run, names the handoff and marks the compaction",
      code == 0 and str(new) in out and "never list writing or checking it" in out and (state(sid) or {}).get("compacting") and not err, err or (code, out, state(sid)))
out, err = run("SessionStart", sid, source="compact", transcript_path=transcript(sid, "claude-opus-5-5", opus_ac))
check("main compact: handoff pasted back as Previous context (no deferral note), state deleted",
      context(out).startswith("Previous context") and "the sample task" in context(out) and "don't write it again" not in context(out) and state(sid) is None and not err,
      err or context(out) or state(sid))


def done_session(sid):
    """A session whose handoff is saved (status done) at the Opus handoff point."""
    run("UserPromptSubmit", sid, transcript_path=transcript(sid, "claude-opus-5-5", opus_at))
    (handoffs / f"handoff-{sid}.md").write_text("# Handoff\n- Goal: the sample task\n")
    run("PostToolUse", sid, tool_name="Write", tool_input={"file_path": str(handoffs / f"handoff-{sid}.md")}, transcript_path=transcript(sid, "claude-opus-5-5", opus_at))
    return (state(sid) or {}).get("status") == "done"


def pre(sid, tokens, model="claude-opus-5-5", trigger="auto", **fields):
    """PreCompact for a session whose last reply read `tokens`; return (exit code, stdout, stderr)."""
    return run_raw("PreCompact", sid, trigger=trigger, transcript_path=transcript(sid, model, tokens), **fields)


def save_handoff(sid, tokens):
    """Write the session's own handoff where the guard named it (the state's path) and let the Write event end the pending state."""
    path = Path(state(sid)["path"])
    path.parent.mkdir(exist_ok=True)
    path.write_text("# Handoff\n- Goal: the sample task\n")
    run("PostToolUse", sid, tool_name="Write", tool_input={"file_path": str(path)}, transcript_path=transcript(sid, "claude-opus-5-5", tokens))
    return path


STARTS = "Instructions from the handoff guard: no handoff was saved"
SAVED = "Instructions from the handoff guard: this session saved a handoff at"

# A compaction without a PreCompact before it (a subagent's, or Claude Code before 2.1.323) leaves no marker: SessionStart(compact)
# does nothing, and the next main-thread event finds the compaction in the main transcript, pastes the handoff, re-arms the guard.
sid = "check-markerless-compact"
ok = done_session(sid)
out, err = run("SessionStart", sid, source="compact", transcript_path=transcript(sid, "claude-opus-5-5", opus_ac))
check("compact with no marker: no paste, state kept", ok and out is None and (state(sid) or {}).get("status") == "done" and not err, err or context(out) or state(sid))
out, err = run("PostToolUse", sid, tool_name="Read", transcript_path=transcript(sid, "claude-opus-5-5", opus_ac, boundary(opus_ac + 1000), reply("claude-opus-5-5", 30_000)))
check("compact with no marker: the next event pastes the handoff and re-arms the guard",
      context(out).startswith("Previous context") and "the sample task" in context(out) and state(sid) is None and not err, err or context(out))

# PreCompact: an auto compaction before the handoff is saved is put off (exit 2), then the model is told once.
sid = "check-defer"
code, out, err = pre(sid, 303_000)
s = state(sid) or {}
pattern = re.escape(str(project / "handoff")) + r"/handoff-\d{8}-\d{6}-" + tag(sid) + r"\.md"
check("defer: an auto compaction with no handoff is put off, state pending, path named",
      code == 2 and not out and s.get("status") == "pending" and s.get("defers") == 1 and s.get("deferred_at") == 303_000 and re.fullmatch(pattern, s.get("path", "")), (code, out, err, s))
out, err = run("PostToolUse", sid, tool_name="Read", transcript_path=transcript(sid, "claude-opus-5-5", 305_000))
s = state(sid) or {}
check("defer: the next event says the autocompact is due now, naming that path, once",
      context(out).startswith("HANDOFF REQUIRED: the autocompact is due now") and s.get("path", "x") in context(out) and s.get("told") and not err, err or context(out) or s)
out, err = run("PostToolUse", sid, tool_name="Read", transcript_path=transcript(sid, "claude-opus-5-5", 305_000))
check("defer: the second event says nothing more", out is None and not err, err or context(out))

# Growth: a deferral lasts while the context stays within 25k of the first block.
sid = "check-defer-growth"
codes = [pre(sid, t)[0] for t in (303_000, 327_999)]
check("growth: blocked at 303000 and 327999 (25k less 1)", codes == [2, 2], codes)
code, out, err = pre(sid, 328_000)
s = state(sid) or {}
check("growth: 328000 is let through, with the stand-in summary instructions and the marker", code == 0 and out.startswith(STARTS) and s.get("compacting") and s.get("standin"), (code, out, err, s))

# Count: at most 12 deferrals, then the compaction runs; SessionStart says the summary stands in for the handoff.
sid = "check-defer-count"
codes = [pre(sid, 303_000)[0] for _ in range(12)]
check("count: 12 requests are put off", codes == [2] * 12, codes)
code, out, err = pre(sid, 303_000)
check("count: the 13th runs, with the stand-in instructions", code == 0 and out.startswith(STARTS), (code, out, err))
out, err = run("SessionStart", sid, source="compact", transcript_path=transcript(sid, "claude-opus-5-5", 303_000))
check("count: SessionStart says the summary stands in, and deletes the state",
      context(out).startswith("The compaction ran before this session's handoff was saved") and state(sid) is None and not err, err or context(out) or state(sid))

# A handoff saved after the first block: the next PreCompact lets the compaction run with instructions to continue from it, and
# SessionStart pastes it with the note not to write it again and to run the skill's step 2 checks.
sid = "check-defer-saved"
pre(sid, 303_000)
path = save_handoff(sid, 305_000)
check("saved after a block: the guard sees it done", (state(sid) or {}).get("status") == "done" and (state(sid) or {}).get("handoff") == str(path), state(sid))
code, out, err = pre(sid, 303_500)
check("saved after a block: the compaction runs, its instructions name the handoff", code == 0 and str(path) in out and "never list writing or checking it" in out and (state(sid) or {}).get("compacting"), (code, out, err))
out, err = run("SessionStart", sid, source="compact", transcript_path=transcript(sid, "claude-opus-5-5", 303_500))
text = context(out)
check("saved after a block: pasted as Previous context, with the deferral note, state deleted",
      text.startswith("Previous context") and "the sample task" in text and "don't write it again" in text and "step 2" in text and state(sid) is None and not err, err or text or state(sid))

# A normal save (no deferral), and a subagent's SessionStart(compact) (agent_id) that must not touch the main thread's state.
sid = "check-compact-agent"
done_session(sid)
code, out, err = pre(sid, opus_ac)
out, err = run("SessionStart", sid, source="compact", agent_id="a1", transcript_path=transcript(sid, "claude-opus-5-5", opus_ac))
check("SessionStart with an agent_id: no output, state kept", out is None and (state(sid) or {}).get("compacting") and not err, err or context(out) or state(sid))
out, err = run("SessionStart", sid, source="compact", transcript_path=transcript(sid, "claude-opus-5-5", opus_ac))
check("normal save: pasted without the deferral note, state deleted",
      context(out).startswith("Previous context") and "don't write it again" not in context(out) and state(sid) is None and not err, err or context(out) or state(sid))

# A manual /compact never blocks: with no handoff it adds nothing; with one it adds the instructions, unless the user gave their own.
sid = "check-manual"
pre(sid, 303_000)
code, out, err = pre(sid, 303_000, trigger="manual")
check("manual while pending: exit 0, no output", code == 0 and not out.strip(), (code, out, err))
save_handoff(sid, 305_000)
code, out, err = pre(sid, 303_000, trigger="manual")
check("manual with a saved handoff: the handoff instructions", code == 0 and out.startswith(SAVED), (code, out, err))
code, out, err = pre(sid, 303_000, trigger="manual", custom_instructions="keep the tests")
check("manual with a saved handoff and the user's own instructions: no output", code == 0 and not out.strip(), (code, out, err))
sid = "check-manual-off"
code, out, err = pre(sid, 100_000, trigger="manual")
check("manual with the state off: exit 0, no output", code == 0 and not out.strip(), (code, out, err))
out, err = run("SessionStart", sid, source="compact", transcript_path=transcript(sid, "claude-opus-5-5", 100_000))
check("manual compact: SessionStart pastes nothing and deletes the state", out is None and state(sid) is None and not err, err or context(out) or state(sid))

# A subagent's PreCompact, the switch HANDOFF_DEFER=0 and a full window with no room left (autocompact 10k below the hard limit).
sid = "check-pre-agent"
code, out, err = pre(sid, 303_000, agent_id="a1")
check("PreCompact with an agent_id: exit 0, no output, no state", code == 0 and not out.strip() and state(sid) is None, (code, out, err))
sid = "check-defer-off"
code, out, err = run_raw("PreCompact", sid, env={"HANDOFF_DEFER": "0"}, trigger="auto", transcript_path=transcript(sid, "claude-opus-5-5", 303_000))
check("HANDOFF_DEFER=0: not blocked, stand-in instructions", code == 0 and out.startswith(STARTS), (code, out, err))
sid = "check-haiku-full"
code, out, err = pre(sid, 967_000, model="claude-haiku-5-5")
check("haiku at 967000 (window 1000000, no room): not blocked, stand-in instructions", code == 0 and out.startswith(STARTS), (code, out, err))

# Compacted while a handoff is still pending (none written): the guard re-arms, nothing to paste, tools unblocked.
sid = "check-pending-compact"
run("UserPromptSubmit", sid, transcript_path=transcript(sid, "claude-opus-5-5", opus_at))
after = transcript(sid, "claude-opus-5-5", opus_at, boundary(opus_ac), reply("claude-opus-5-5", 30_000))
out, err = run("PreToolUse", sid, tool_name="Edit", tool_input={"file_path": str(project / "app.py")}, transcript_path=after)
out2, err2 = run("PostToolUse", sid, tool_name="Edit", transcript_path=after)
check("pending compact: tool allowed, guard re-armed, nothing pasted", out is None and out2 is None and state(sid) is None and not (err or err2), err or err2 or out or out2)

# An advisor call: the response's top-level usage adds up both its message iterations (about twice the context); the guard
# counts the last one only (Nov 12 2026: a 172k context read as 352k fired the handoff early).
sid = "check-advisor"
out, err = run("UserPromptSubmit", sid, transcript_path=transcript(sid, "claude-opus-5-5", 1000, advisor_reply("claude-opus-5-5", 172_000, 175_000, 177_000)))
check("advisor: 175k context (347k summed) gives no notice", out is None and state(sid) is None and not err, err or context(out))
out, err = run("UserPromptSubmit", sid, transcript_path=transcript(sid, "claude-opus-5-5", 1000, advisor_reply("claude-opus-5-5", opus_at - 4000, opus_at, 200_000)))
check(f"advisor: HANDOFF REQUIRED at {opus_at} from the last iteration", required(out, opus_at, opus_ac) and not err, err or context(out))

# Parallel sessions in one checkout share handoff/ (Nov 13 2026: another session's handoff-20261113-003000.md was recorded for
# this session's 001459). Only this session's own handoff counts, whatever the names or times of the others.
shared = home / "shared"
subprocess.run(["git", "init", "-q", str(shared)], check=True)
(shared / ".gitignore").write_text("handoff/\n")
(shared / "handoff").mkdir()
mine, other = "check-parallel-mine", "check-parallel-other"
run("UserPromptSubmit", mine, root=shared, transcript_path=transcript(mine, "claude-opus-5-5", opus_at))
theirs = shared / "handoff" / "handoff-20261113-003000.md"
theirs.write_text("# Handoff\n- Goal: the other session's task\n")
out, err = run("PostToolUse", mine, root=shared, tool_name="Read", transcript_path=transcript(mine, "claude-opus-5-5", opus_at))
check("parallel: another session's new handoff leaves this one pending", out is None and (state(mine) or {}).get("status") == "pending" and not err, err or context(out) or state(mine))
own = shared / "handoff" / "handoff-20261113-001459.md"
own.write_text("# Handoff\n- Goal: this session's task\n")
out, err = run("PostToolUse", mine, root=shared, tool_name="Write", tool_input={"file_path": str(own)}, transcript_path=transcript(mine, "claude-opus-5-5", opus_at))
s = state(mine) or {}
check("parallel: this session's Write is recorded, not the later-named file of another session",
      context(out).startswith("Handoff saved") and s.get("handoff") == str(own) and not err, err or (context(out), s))
run_raw("PreCompact", mine, root=shared, trigger="auto", transcript_path=transcript(mine, "claude-opus-5-5", opus_ac))
out, err = run("SessionStart", mine, root=shared, source="compact", transcript_path=transcript(mine, "claude-opus-5-5", opus_ac))
check("parallel: its own handoff is the one pasted back", "this session's task" in context(out) and "other session" not in context(out) and not err, err or context(out))

# A handoff written by shell with this session's tag counts; the other session's live handoff and this one survive pruning,
# which goes by mtime, not by name.
run("UserPromptSubmit", other, root=shared, transcript_path=transcript(other, "claude-opus-5-5", opus_at))
tagged = shared / "handoff" / f"handoff-20261113-002000-{tag(other)}.md"
tagged.write_text("# Handoff\n- Goal: the other session's task\n")
out, err = run("PostToolUse", other, root=shared, tool_name="Bash", tool_input={"command": f"cat > {tagged}"}, transcript_path=transcript(other, "claude-opus-5-5", opus_at))
check("tagged: a shell-written handoff named with the session tag is recorded", (state(other) or {}).get("handoff") == str(tagged) and not err, err or context(out) or state(other))
for n in range(4):  # newer handoffs from finished sessions, named after this session's
    f = shared / "handoff" / f"handoff-20261113-01{n}000.md"
    f.write_text("old\n")
    os.utime(f, (time.time() - 60 + n, time.time() - 60 + n))
for f in (own, theirs, tagged):
    os.utime(f, (time.time() - 3600, time.time() - 3600))
sid3 = "check-parallel-third"
run("UserPromptSubmit", sid3, root=shared, transcript_path=transcript(sid3, "claude-opus-5-5", opus_at))
third = shared / "handoff" / f"handoff-20261113-020000-{tag(sid3)}.md"
third.write_text("# Handoff\n")
run("PostToolUse", sid3, root=shared, tool_name="Bash", tool_input={"command": "true"}, transcript_path=transcript(sid3, "claude-opus-5-5", opus_at))
left = {p.name for p in (shared / "handoff").glob("handoff-*.md")}
# `own` belonged to `mine`, which compacted above: its state is gone, so the handoff is no longer live and goes by mtime.
check("prune: live sessions' handoffs kept, the rest cut to the newest 3 by mtime",
      {tagged.name, third.name} <= left and theirs.name not in left and own.name not in left and len(left) == 4, sorted(left))

if not failed:
    shutil.rmtree(home)  # kept on a failure, to look at
print(f"RESULT: {'PASS' if not failed else f'FAIL ({failed} failed; files in {home})'}")
sys.exit(1 if failed else 0)
