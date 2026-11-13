#!/usr/bin/env python3
"""Handoff guard: 35k tokens before the autocompact (which fires 33k below the /autocompact window), make Claude write and commit
a handoff, then paste that handoff back in after the compaction so the next context has the full picture. Every model gets it,
each at the points its own window gives. byte-stack's hooks/check-handoff-guard.py runs it on sample sessions.

One script for every event (dispatches on hook_event_name):
  UserPromptSubmit, PostToolUse  measure context; at the threshold mark the session "pending" and tell Claude to run the SKILL
  PreToolUse                     while pending, only handoff work is allowed
  PostToolUse                    while pending, a commit touching handoff/ (or, where handoff/ is gitignored or outside git, a
                                 new or changed file there) marks it "done" and records the handoff path; work then carries on
                                 until autocompact. An ignored or non-git handoff/ is pruned to the newest KEEP files then.
  UserPromptSubmit, PostToolUse  done and still not compacted at the update point: pending again (once) until the work since the
                                 handoff is appended to it under "## Since the handoff" and committed
  SessionStart(compact)          paste the recorded handoff into the compacted context as "Previous context", if the compaction
                                 is surely the main thread's (a subagent's compaction runs it too; see main_compacting)
  UserPromptSubmit, PostToolUse  the main transcript shows a compaction since the guard armed: re-arm it (delete the state), and
                                 paste the handoff if SessionStart didn't
Context size is the last main-thread response's, counting only its last model iteration (an advisor call adds more; see
usage_tokens). The session_id stays the same across autocompact, so the state file links the handoff to the compaction.
Subagents (events with an agent_id) are ignored: never measured, blocked or counted as the handoff, though they share the session_id.
State: ~/.claude/handoff-state/<session_id>.json. Escape hatch: delete it, or set HANDOFF_AT=0 to switch the guard off.
The byte-stack plugin (Bytefloww1013/josh-skills) ships this file as hooks/handoff-guard.py, registered in its hooks/hooks.json,
so every project that enables the plugin has the guard. A project may also commit a byte-identical copy at
.claude/hooks/handoff-guard.py, registered in its .claude/settings.json (bphs-connect does: cloud sessions don't install
plugins). The plugin's copy then does nothing in that project, so one guard runs. SKILL follows from where this file is.
"""
import json, os, re, subprocess, sys, time
from datetime import datetime
from pathlib import Path

# Real autocompact point, as Claude Code computes it (and the /context panel shows as "Autocompact buffer" = 33k):
# window - min(maxOutputTokens, 20000) summary reserve - 13000 buffer. Seen in the transcripts: window 150k fired at ~117k,
# 200k at ~167k, 293k at ~260k, 335k at ~302k. Each model's window is read from the settings `/autocompact <n>` writes
# (modelSettings.<model>.autoCompactWindow), so the thresholds follow the session's model: 335000 -> autocompact 302000,
# handoff 267000, update 296000; 150000 -> 117000, 82000, 111000.
# With no setting, Claude Code (2.1.322) uses the model's context window: 1M for current models, but 200000 for a model it doesn't
# recognize or an account without 1M context. 200000 is the smallest, so the handoff never lands past a real autocompact.
DEFAULT_WINDOW = int(os.environ.get("HANDOFF_WINDOW", 200_000))  # when no settings file names the model's window
SUMMARY_RESERVE, BUFFER = 20_000, 13_000
HANDOFF_MARGIN = 35_000  # room to write, check and save the handoff before the autocompact
UPDATE_MARGIN = 6_000  # still not compacted this close to it: append what was done since
# The skill the notices name: the plugin's own, namespaced, when this file is in the plugin (its parent folder holds
# .claude-plugin/), else the project's copy. Not `handoff`, which a user-level skill of that name would outrank.
SKILL = "byte-stack:byte-handoff" if (Path(__file__).resolve().parent.parent / ".claude-plugin").is_dir() else "byte-handoff"
STATE_DIR = Path.home() / ".claude" / "handoff-state"
READ_ONLY = {"Read", "Grep", "Glob", "LS", "Skill", "ToolSearch", "ReadNotifications"}
SHELL_OK = {"git", "mkdir", "date", "ls", "pwd", "cat", "head", "tail", "wc", "echo", "true", "test", "stat", "grep", "for", "done"}
SHELL_KEYWORDS = {"do"}  # stripped so the command after it is checked: `for p in a b; do test -e $p; done`
RESUME_MAX_CHARS = 9000  # hook additionalContext is capped near 10k
GIT_OK = {"status", "log", "diff", "add", "commit", "rev-parse", "show", "branch", "check-ignore"}
KEEP = 3  # handoffs kept on disk where handoff/ is gitignored or outside git (the user's rule, Oct 19 2026)


def project_root(cwd):
    try:
        out = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return out.stdout.strip(), True
    except Exception:
        pass
    return cwd, False


def compact_window(model, root):
    """The model's autoCompactWindow, as Claude Code ranks settings: project local, project, then user (where /autocompact writes).
    In each file a modelSettings entry for the model wins over a top-level autoCompactWindow (the cloud container sets that)."""
    for f in (Path(root, ".claude", "settings.local.json"), Path(root, ".claude", "settings.json"), Path.home() / ".claude" / "settings.json"):
        try:
            settings = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        for key, val in (settings.get("modelSettings") or {}).items():
            if model and key in model and isinstance(val, dict) and val.get("autoCompactWindow"):
                return int(val["autoCompactWindow"])
        if settings.get("autoCompactWindow"):
            return int(settings["autoCompactWindow"])
    return DEFAULT_WINDOW


def thresholds(model, root):
    """(autocompact, handoff, update) points in context tokens; HANDOFF_AT / HANDOFF_UPDATE_AT override the last two."""
    autocompact = compact_window(model, root) - SUMMARY_RESERVE - BUFFER
    handoff = int(os.environ.get("HANDOFF_AT") or autocompact - HANDOFF_MARGIN)
    update = int(os.environ.get("HANDOFF_UPDATE_AT") or autocompact - UPDATE_MARGIN)
    return autocompact, handoff, update


def usage_tokens(u):
    """Context size of one API response. A response that called a server tool such as the advisor is several model iterations
    (message, advisor_message, message): the top-level fields add them all up, about twice the real context (a 172k context read
    as 352k, Nov 12 2026), so the size is the last "message" iteration's. Without iterations, the top-level fields."""
    its = [i for i in (u.get("iterations") or []) if isinstance(i, dict) and i.get("type") == "message"]
    u = its[-1] if its else u
    return u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)


def epoch(stamp):
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def read_transcript(transcript, sidechain=False):
    """(context size, model, time of the newest compaction) from a transcript's tail: the size is the last assistant usage after
    that compaction (0 if none came after it). The main transcript holds only the main thread's compactions: a subagent's go to
    its own file under <session>/subagents/, read with sidechain=True (its entries are marked isSidechain)."""
    try:
        with open(transcript, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4_000_000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return 0, "", None
    tokens, model = None, ""
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("subtype") == "compact_boundary":
            return tokens or 0, model, epoch(e.get("timestamp"))
        u = (e.get("message") or {}).get("usage") if e.get("type") == "assistant" and (sidechain or not e.get("isSidechain")) else None
        if u and tokens is None:
            tokens, model = usage_tokens(u), e["message"].get("model", "")
    return tokens or 0, model, None


def near_autocompact(transcript, root, sidechain=False):
    """The transcript's thread has not compacted since its last usage, which is within UPDATE_MARGIN of its autocompact point:
    it is the one compacting now, or will be on its next request."""
    tokens, model, _ = read_transcript(transcript, sidechain)
    return tokens > 0 and tokens >= thresholds(model, root)[0] - UPDATE_MARGIN


def main_compacting(transcript, root):
    """Whether a SessionStart(compact) is the main thread's. Claude Code (2.1.322) runs SessionStart(compact) for a subagent's
    compaction too, with the same session_id and transcript_path and no agent_id, so the event can't say; and the main transcript
    gets its compact_boundary only after the hooks have run. So: the main thread is at its autocompact point and no subagent
    written in the last 10 minutes is at its own. Both or neither: not sure, so False (the next main-thread event finds the
    boundary and pastes then)."""
    if not near_autocompact(transcript, root):
        return False
    subagents = Path(str(transcript)).with_suffix("") / "subagents"
    recent = [f for f in subagents.glob("*.jsonl") if f.stat().st_mtime > time.time() - 600] if subagents.is_dir() else []
    return not any(near_autocompact(f, root, sidechain=True) for f in recent)


def runs_own_copy(project):
    """A project that commits its own copy at .claude/hooks/ and registers it in its settings runs that copy instead. A copy
    nothing registers (the old user-level one, seen from a session started in the home folder) doesn't count."""
    own = project / ".claude" / "hooks" / "handoff-guard.py"
    if not own.exists() or own.resolve() == Path(__file__).resolve():
        return False
    for name in ("settings.json", "settings.local.json"):
        try:
            if ".claude/hooks/handoff-guard.py" in (project / ".claude" / name).read_text():
                return True
        except OSError:
            pass
    return False


def handoff_local(root, is_git):
    """handoff/ outside git or gitignored: handoffs there are never committed."""
    return not is_git or subprocess.run(["git", "-C", root, "check-ignore", "-q", "handoff/"], timeout=5).returncode == 0


def handoff_changed_since(root, local, since):
    d = Path(root) / "handoff"
    if not local:
        out = subprocess.run(["git", "-C", root, "log", "-1", "--format=%ct", "--", "handoff"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip().isdigit() and int(out.stdout) >= int(since)
    return any(p.stat().st_mtime >= since for p in d.glob("handoff-*.md"))


def prune(root):
    for old in sorted((Path(root) / "handoff").glob("handoff-*.md"))[:-KEEP]:  # names sort by their timestamp
        old.unlink(missing_ok=True)


def newest_handoff(root):
    files = sorted((Path(root) / "handoff").glob("handoff-*.md"))
    return str(files[-1]) if files else None


def say(event, text, **extra):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text, **extra}}))


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))


def bash_allowed(cmd):
    # shortcut: checks command names only, so `echo x > file` can still write anywhere; fine for keeping Claude on task, not a sandbox
    for seg in re.split(r"&&|\|\||;|\||\n", cmd):
        words = seg.strip(" \t(){}").split()  # a ( ) or { } group's brackets aren't commands; the commands inside are checked
        if words[:1] == ["rtk"]:
            words = words[1:]
        while words and (re.match(r"^[A-Z_]+=", words[0]) or words[0] in SHELL_KEYWORDS):
            words = words[1:]
        if not words:
            continue
        if words[0] not in SHELL_OK:
            return False
        if words[0] == "git":
            sub = [w for w in words[1:] if not w.startswith("-")]
            # skip "-C <dir>"
            if "-C" in words[1:3]:
                sub = sub[1:]
            if not sub or sub[0] not in GIT_OK:
                return False
    return True


def pre_tool(data, state, root):
    tool, inp = data.get("tool_name", ""), data.get("tool_input") or {}
    if tool.startswith("mcp__ccd_") or tool in READ_ONLY or tool.startswith("mcp__codegraph__"):
        return
    if tool in ("Write", "Edit") and str(Path(inp.get("file_path", "")).resolve()).startswith(str(Path(root, "handoff").resolve()) + os.sep):
        return
    if tool == "Bash" and bash_allowed(inp.get("command", "")):
        return
    if state.get("updated"):
        return deny(f"Context passed {state.get('at', 'the update')} tokens: only handoff work is allowed now. Append \"## Since the handoff\" to {state['handoff']} (the {SKILL} skill, step 5) and commit it unless handoff/ is gitignored, then carry on with the task.")
    deny(f"Context passed {state.get('at', 'the handoff')} tokens: only handoff work is allowed now. Run the {SKILL} skill (write {root}/handoff/handoff-<timestamp>.md, check it, commit it unless handoff/ is gitignored), then carry on with the task.")


def resume_text(path):
    text = Path(path).read_text(errors="replace")
    if len(text) > RESUME_MAX_CHARS:
        text = text[:RESUME_MAX_CHARS] + f"\n\n[truncated; read the rest of {path}]"
    return (f"Previous context (handoff from {path}, written just before this compaction):\n\n{text}\n\n"
            "Use it with the compact summary: the summary also covers work done after the handoff, so where they differ the summary is newer. "
            "Continue the task from where it stands; tell the user in one line that you resumed with this handoff.")


def main():
    data = json.load(sys.stdin)
    # A subagent's events carry its agent_id but the parent's session_id, so they would share the parent's state file: a
    # pending main thread then denied every running subagent's tools (Oct 23 2026). The guard is for the main thread only.
    if os.environ.get("HANDOFF_AT", "").strip() == "0" or data.get("agent_id"):
        return
    event, sid = data.get("hook_event_name"), data.get("session_id", "unknown")
    root, is_git = project_root(data.get("cwd") or os.getcwd())
    if runs_own_copy(Path(os.environ.get("CLAUDE_PROJECT_DIR") or root)):
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    sfile = STATE_DIR / f"{sid}.json"
    state = json.loads(sfile.read_text()) if sfile.exists() else {"status": "off"}

    transcript = data.get("transcript_path", "")
    if event == "SessionStart":
        # A subagent's compaction runs this too (see main_compacting), so the state stays: the next main-thread event re-arms
        # the guard once the main transcript shows the compaction. The handoff is pasted now only if the compaction is surely
        # the main thread's, so it never lands in a subagent's context; otherwise it is pasted at that next event.
        if data.get("source") == "compact" and state["status"] != "off":
            path = state.get("handoff")
            if path and Path(path).exists() and main_compacting(transcript, root):  # also mid-update: the first version is good
                state["pasted"] = time.time()
                sfile.write_text(json.dumps(state))
                say(event, resume_text(path))
        for old in STATE_DIR.glob("*"):  # tidy state from sessions that ended
            if old.is_file() and old.stat().st_mtime < time.time() - 3 * 86400:
                old.unlink(missing_ok=True)
        return

    # One read of the transcript per event; PreToolUse reads it only while pending, the only time it acts.
    scanned = event in ("UserPromptSubmit", "PostToolUse") or (event == "PreToolUse" and state["status"] == "pending")
    tokens, model, compacted = read_transcript(transcript) if scanned else (0, "", None)
    if state["status"] != "off" and compacted and compacted > state.get("armed", state.get("since", 0)):
        # The main thread compacted since the guard armed: re-arm it, and paste the handoff unless SessionStart did for this
        # compaction (its boundary is stamped just before the SessionStart hooks run). PreToolUse lets the tool through and
        # leaves both to the PostToolUse after it.
        if event == "PreToolUse":
            return
        sfile.unlink(missing_ok=True)
        path, pasted = state.get("handoff"), state.get("pasted")
        if path and Path(path).exists() and not (pasted and compacted - 30 <= pasted <= compacted + 120):
            return say(event, resume_text(path))
        state = {"status": "off"}

    if event == "PreToolUse":
        if state["status"] == "pending":
            pre_tool(data, state, root)
        return

    measure = state["status"] == "off" or (state["status"] == "done" and not state.get("updated"))
    if measure and event in ("UserPromptSubmit", "PostToolUse"):
        autocompact, handoff_at, update_at = thresholds(model, root)
        if state["status"] == "done" and tokens >= update_at:
            state.update(status="pending", since=time.time(), updated=True, at=update_at)
            sfile.write_text(json.dumps(state))
            return say(event, f"HANDOFF UPDATE REQUIRED: context is {tokens} tokens and autocompact (at {autocompact}) hasn't run yet. Pause at a safe point and append a \"## Since the handoff\" section to {state['handoff']}: every action completed since it was written ({SKILL} skill, step 5), with Next steps and Watch out corrected if they changed. Commit only that file, unless handoff/ is gitignored. Other tools are blocked until then.")
        if state["status"] == "off" and tokens >= handoff_at:
            now = time.time()
            sfile.write_text(json.dumps({"status": "pending", "since": now, "armed": now, "root": root, "at": handoff_at}))
            return say(event, f"HANDOFF REQUIRED: context is {tokens} tokens; autocompact runs at {autocompact}. Pause the current task at a safe point and run the {SKILL} skill: write {root}/handoff/handoff-<YYYYMMDD-HHMMSS>.md, check it and commit only that file (skip the commit if handoff/ is gitignored). Other tools are blocked until then; afterwards carry on with the task.")

    local = state["status"] == "pending" and event == "PostToolUse" and handoff_local(root, is_git)
    if state["status"] == "pending" and event == "PostToolUse" and handoff_changed_since(root, local, state["since"]):
        state.update(status="done", handoff=state.get("handoff") or newest_handoff(root))
        sfile.write_text(json.dumps(state))
        if local:
            prune(root)
        return say(event, f"Handoff {'update ' if state.get('updated') else ''}{'saved' if local else 'committed'} ({state['handoff']}). Tools are unblocked: carry on with the task. After the autocompact the handoff is pasted back in as \"Previous context\".")

    if state["status"] == "pending" and event == "UserPromptSubmit":
        say(event, "Reminder: the handoff is still required; finish it before other work.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never break the session over a guard bug
        print(f"handoff-guard: {exc}", file=sys.stderr)
