#!/usr/bin/env python3
"""Handoff guard: 35k tokens before the autocompact (which fires 33k below the window Claude Code uses for the model), make
Claude write and commit a handoff, then paste that handoff back in after the compaction so the next context has the full
picture. Every model gets it, each at the points its own window gives. byte-stack's hooks/check-handoff-guard.py runs it on
sample sessions.

One script for every event (dispatches on hook_event_name):
  UserPromptSubmit, PostToolUse  measure context; at the threshold mark the session "pending" and tell Claude to run the SKILL
  PreToolUse                     while pending, only handoff work is allowed
  PostToolUse                    while pending, a commit of this session's handoff (or, where handoff/ is gitignored or outside
                                 git, a new or changed one) marks it "done" and records its path; work then carries on until
                                 autocompact. An ignored or non-git handoff/ is pruned to the newest KEEP files then.
  PreCompact (auto)              no handoff saved yet: put the compaction off (exit 2) while the context grows less than
                                 DEFER_GROWTH, for at most DEFER_MAX requests, and tell Claude to write the handoff now. Past
                                 those bounds, or with no room, let it run and give the summary instructions. Always notes
                                 "compacting" in the state: the marker SessionStart(compact) goes by. A manual /compact is
                                 never put off; it gets the instructions only if a handoff is saved and no instructions of its own.
  SessionStart(compact)          with a recent "compacting" marker: delete the state (re-arms the guard) and paste the recorded
                                 handoff as "Previous context", or say the summary stands in for it. A subagent's compaction
                                 runs it too, but never PreCompact, so it has no marker and does nothing.
  UserPromptSubmit, PostToolUse  the main transcript shows a compaction since the guard armed (SessionStart didn't run, before
                                 Claude Code 2.1.323): re-arm it (delete the state), and paste the handoff
There is no update step and no Stop handler: a finished `-p` task never needed the compaction, and an interactive session's next
prompt carries the notice.
Context size is the last main-thread response's, counting only its last model iteration (an advisor call adds more; see
usage_tokens). The session_id stays the same across autocompact, so the state file links the handoff to the compaction.
Subagents (events with an agent_id) are ignored: never measured, blocked or counted as the handoff, though they share the session_id.
A handoff is this session's only if its name ends with the session tag (handoff-<YYYYMMDD-HHMMSS>-<first 8 of session_id>.md, the
name the notices give) or this session's own Write or Edit made it. handoff/ is shared by every session in the checkout, so the
newest file there is often another session's (Nov 13 2026: a parallel session's handoff-20261113-003000.md was recorded, and
pasted back, in place of this session's 001459).
State: ~/.claude/handoff-state/<session_id>.json. Escape hatch: delete it, or set HANDOFF_AT=0 to switch the guard off.
The byte-stack plugin (Bytefloww1013/josh-skills) ships this file as hooks/handoff-guard.py, registered in its hooks/hooks.json,
so every project that enables the plugin has the guard. A project may also commit a byte-identical copy at
.claude/hooks/handoff-guard.py, registered in its .claude/settings.json (bphs-connect does: cloud sessions don't install
plugins). The plugin's copy then does nothing in that project, so one guard runs. SKILL follows from where this file is.
"""
import json, math, os, re, subprocess, sys, time
from datetime import datetime
from pathlib import Path

# Where Claude Code autocompacts (the /context panel shows the gap as the 33k "Autocompact buffer"), read from its 2.1.323
# binary and checked against compact_boundary.preTokens in lab runs (Nov 14 2026, 0-1.6k above the formula):
#   window = min(configured window, the model's window); a configured window is clamped to 100000-1000000
#   autocompact = window - min(maxOutputTokens, 20000) - 13000
#   with CLAUDE_AUTOCOMPACT_PCT_OVERRIDE: min(floor((window - reserve) * pct / 100), window - reserve - 13000)
# 335000 -> 302000 (handoff 267000); 150000 -> 117000 (82000); no setting on a 1M-default model -> ~967000 (932000).
# The configured window comes from CLAUDE_CODE_AUTO_COMPACT_WINDOW, else the settings files (configured_window). A setting can't
# raise the window above the model's, so a 335000 entry on a 200k model compacts at ~167k: model_window caps it.
BUFFER = 13_000
HANDOFF_MARGIN = 35_000  # room to write, check and save the handoff before the autocompact
DEFER_GROWTH = 25_000  # put a compaction off only while the context stays within this of where the first block found it
DEFER_MAX = 12         # and for at most this many requests: Claude Code has no circuit breaker (lab E4: 27 blocks)
HEADROOM = 30_000      # and only this far below the model's hard limit (model window - 23000)
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


def parse_window(val):
    """A configured window as Claude Code reads it: a number, or a string such as "335000", "335k", "1M"; "auto" means the
    model's own window. Numbers are clamped to 100000-1000000 (lab runs: 60000, 80000 and 100000 all compacted at ~67k).
    Anything else, a bool included, is None (not a window)."""
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        n = val
    elif isinstance(val, str):
        if val.strip().lower() == "auto":
            return "auto"
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\s*", val)
        if not m:
            return None
        n = float(m.group(1)) * {"": 1, "k": 1_000, "m": 1_000_000}[m.group(2).lower()]
    else:
        return None
    if not math.isfinite(n) or n <= 0:
        return None
    return int(min(max(n, 100_000), 1_000_000))


def canonical(model):
    """A model id without a trailing [1m] or -YYYYMMDD, lowercased: how settings keys and transcript ids are compared."""
    return re.sub(r"-\d{8}$", "", re.sub(r"\[1m\]$", "", (model or "").strip().lower()))


def env_int(name, default=None):
    value = os.environ.get(name, "").strip()
    return int(value) if value.isdigit() else default


def model_window(model):
    """The context window the model runs with. Docs (code.claude.com/docs/en/model-config.md, Nov 14 2026): "Fable models,
    Sonnet 5 and later, Haiku 5.5, and Opus 4.7 and later run with the 1M window by default"; Opus 4.6 and Sonnet 4.6 get 1M only
    with [1m]; CLAUDE_CODE_DISABLE_1M_CONTEXT caps them at 200k. A future model family needs a line in the regex; until then it
    gets the early 200k. (Claude Code assumes 1M for an unknown id since 2.1.323, so for such a model this is early: safe.)"""
    if os.environ.get("CLAUDE_CODE_DISABLE_1M_CONTEXT", "").strip().lower() in ("1", "true", "yes"):
        return 200_000
    if "[1m]" in (model or "").lower():
        return 1_000_000
    if re.search(r"claude-(fable-|sonnet-([5-9]|\d\d)|haiku-(5-[5-9]|[6-9]|\d\d)|opus-(4-[7-9]|[5-9]|\d\d))", canonical(model)):
        return 1_000_000
    return env_int("CLAUDE_CODE_MAX_CONTEXT_TOKENS") or env_int("HANDOFF_WINDOW") or 200_000


def configured_window(model, root):
    """(window or None, source) as Claude Code resolves a configured autoCompactWindow: CLAUDE_CODE_AUTO_COMPACT_WINDOW beats
    every file; else the first of managed, project local, project, user settings (highest precedence first; checked against
    xQt() in the 2.1.323 binary) that holds one. In a file a modelSettings entry for the model (its exact key first, as Claude
    Code's Oco() does, else a key equal after canonical()) beats the top-level autoCompactWindow. "auto" -> None: the model's
    own window. Nothing -> (None, "default")."""
    def found(w, source):
        return (None if w == "auto" else w), source

    env = parse_window(os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW"))
    if env is not None:
        return found(env, "env")
    for f in (Path("/etc/claude-code/managed-settings.json"), Path("/Library/Application Support/ClaudeCode/managed-settings.json"),
              Path(root, ".claude", "settings.local.json"), Path(root, ".claude", "settings.json"), Path.home() / ".claude" / "settings.json"):
        try:
            settings = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(settings, dict):
            continue
        per_model = settings.get("modelSettings")
        per_model = {k: v for k, v in per_model.items() if isinstance(v, dict)} if isinstance(per_model, dict) else {}
        if model:
            for same in (lambda k: k == model, lambda k: canonical(k) == canonical(model)):
                for key, val in per_model.items():
                    w = parse_window(val.get("autoCompactWindow")) if same(key) else None
                    if w is not None:
                        return found(w, str(f))
        w = parse_window(settings.get("autoCompactWindow"))
        if w is not None:
            return found(w, str(f))
    return None, "default"


def thresholds(model, root, ceiling=None):
    """(autocompact, handoff, window, source): the points in context tokens, and the window they came from. HANDOFF_AT overrides
    the handoff point. ceiling is the last auto compaction's preTokens in this transcript: a window the hook can't read (a
    --autocompact flag, --settings, a server-pushed window) shows up there, and min() only ever lowers the point."""
    mw = model_window(model)
    cw, source = configured_window(model, root)
    window = min(cw or mw, mw)  # Claude Code caps a setting at the model's window
    out = env_int("CLAUDE_CODE_MAX_OUTPUT_TOKENS")  # a bad value must not kill the guard
    reserve = min(20_000, out) if out and out > 0 else 20_000
    effective = window - reserve
    autocompact = effective - BUFFER
    pct = env_int("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE")
    if pct and 1 <= pct <= 100:
        autocompact = min(effective * pct // 100, effective - BUFFER)
    if ceiling:  # an auto compaction already ran lower in this transcript
        autocompact = min(autocompact, ceiling)
    handoff = env_int("HANDOFF_AT") or autocompact - HANDOFF_MARGIN
    return autocompact, handoff, window, source


def usage_tokens(u):
    """Context size of one API response. A response that called a server tool such as the advisor is several model iterations
    (message, advisor_message, message): the top-level fields add them all up, about twice the real context (a 172k context read
    as 352k, Nov 12 2026), so the size is the last "message" iteration's. Without iterations, the top-level fields. The reply's
    own output_tokens count too: it is in the context at the next request. Over 485 real auto compactions, preTokens minus the
    input and cache tokens alone was p50 2.9k, p90 9.4k, p99 31.8k; with output_tokens added the reading never overshot
    (min +1) and the p50 shrank to 1.1k, p90 4.1k, p99 12.9k (Nov 14 2026)."""
    its = [i for i in (u.get("iterations") or []) if isinstance(i, dict) and i.get("type") == "message"]
    u = its[-1] if its else u
    return u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("output_tokens", 0)


def epoch(stamp):
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def read_transcript(transcript, sidechain=False):
    """(context size, model, time of the newest compaction, ceiling) from a transcript's tail: the size is the last assistant
    usage after that compaction (0 if none came after it). The ceiling is that compaction's preTokens when it was an auto one
    and the reply before it was the same model's, else None. The main transcript holds only the main thread's compactions: a
    subagent's go to its own file under <session>/subagents/, read with sidechain=True (its entries are marked isSidechain)."""
    try:
        with open(transcript, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4_000_000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return 0, "", None, None
    tokens, model, boundary = None, "", None
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if boundary is None and e.get("subtype") == "compact_boundary":
            boundary = e
            meta = e.get("compactMetadata") or {}
            if meta.get("trigger") != "auto" or not isinstance(meta.get("preTokens"), int) or not model:
                return tokens or 0, model, epoch(e.get("timestamp")), None
            continue
        u = (e.get("message") or {}).get("usage") if e.get("type") == "assistant" and (sidechain or not e.get("isSidechain")) else None
        if not u:
            continue
        if boundary is None:
            if tokens is None:
                tokens, model = usage_tokens(u), e["message"].get("model", "")
            continue
        ceiling = boundary["compactMetadata"]["preTokens"] if e["message"].get("model", "") == model else None
        return tokens or 0, model, epoch(boundary.get("timestamp")), ceiling
    if boundary is not None:
        return tokens or 0, model, epoch(boundary.get("timestamp")), None
    return tokens or 0, model, None, None


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


def session_tag(sid):
    """The suffix that marks a handoff as this session's: the session_id's first 8 letters or digits."""
    return re.sub(r"[^0-9A-Za-z]", "", sid)[:8] or "unknown"


def handoff_path(root, sid):
    """The exact file the notices name. While pending, the allowlist refuses the skill's own step-1 commands (`cd`, a heredoc,
    `root=$(...)`), and a model whose `date` was denied made up the time: 3 of 4 delegate handoffs had one (Nov 14 2026)."""
    return Path(root, "handoff", f"handoff-{datetime.now():%Y%m%d-%H%M%S}-{session_tag(sid)}.md")


def in_handoff_dir(root, path):
    try:
        p = Path(path).resolve()
    except (OSError, TypeError, ValueError):
        return False
    return p.parent == Path(root, "handoff").resolve() and re.fullmatch(r"handoff-.+\.md", p.name) is not None


def own_handoffs(root, sid, state):
    """This session's handoffs: the one it already recorded, else every file named with its tag plus the last one its own Write
    or Edit made. Never another session's, whatever its name or time."""
    if state.get("handoff"):
        return [Path(state["handoff"])]
    files = set((Path(root) / "handoff").glob(f"handoff-*-{session_tag(sid)}.md"))
    if state.get("wrote"):
        files.add(Path(state["wrote"]))
    return [f for f in files if f.is_file()]


def changed_at(root, local, path):
    """When the handoff last changed: its mtime where handoff/ is never committed, else its last commit's time (None if none)."""
    if local:
        return path.stat().st_mtime
    out = subprocess.run(["git", "-C", root, "log", "-1", "--format=%ct", "--", str(path)], capture_output=True, text=True, timeout=5)
    return int(out.stdout) if out.stdout.strip().isdigit() else None


def own_handoff_since(root, local, since, files):
    """The newest of files saved (or committed) since the guard went pending, or None."""
    times = [(t, str(f)) for f in files if (t := changed_at(root, local, f)) is not None and t >= (since if local else int(since))]
    return max(times)[1] if times else None


def live_handoffs():
    """Handoffs some session's state still points to: pasted back at its autocompact, so pruning must not take them."""
    live = set()
    for f in STATE_DIR.glob("*.json"):
        try:
            s = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        live.update(str(Path(s[k]).resolve()) for k in ("handoff", "wrote") if s.get(k))
    return live


def prune(root):
    """Keep the newest KEEP handoffs by mtime (a name's timestamp can be wrong or another session's), and any a session still needs."""
    files = sorted((Path(root) / "handoff").glob("handoff-*.md"), key=lambda p: p.stat().st_mtime)
    live = live_handoffs()
    for old in files[:-KEEP]:
        if str(old.resolve()) not in live:
            old.unlink(missing_ok=True)


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
    path = state.get("path") or handoff_path(root, data.get("session_id", "unknown"))
    deny(f"Context passed {state.get('at', 'the handoff')} tokens: only handoff work is allowed now. Run the {SKILL} skill (write exactly {path} with the Write tool, check it, commit it unless handoff/ is gitignored), then carry on with the task.")


def resume_text(path):
    text = Path(path).read_text(errors="replace")
    if len(text) > RESUME_MAX_CHARS:
        text = text[:RESUME_MAX_CHARS] + f"\n\n[truncated; read the rest of {path}]"
    return (f"Previous context (handoff from {path}, written just before this compaction):\n\n{text}\n\n"
            "Use it with the compact summary: the summary also covers work done after the handoff, so where they differ the summary is newer. "
            "Continue the task from where it stands; tell the user in one line that you resumed with this handoff.")


def summary_instructions(state):
    """What to tell the compaction's summarizer (PreCompact stdout): continue from the saved handoff, or stand in for it."""
    if state:
        path = state["handoff"]
        at = datetime.fromtimestamp(Path(path).stat().st_mtime).strftime("%H:%M:%S")
        return (f"Instructions from the handoff guard: this session saved a handoff at {path} ({at}); it is pasted back after this "
                "compaction. If you don't see it being written, that happened in the latest messages, which are kept word for word "
                "after this summary: treat it as saved and never list writing or checking it as a next step. Make the summary "
                "continue from it: list every action completed after it was written (paths, short shas, commands and results, "
                "decisions), then the exact next step.")
    return ("Instructions from the handoff guard: no handoff was saved before this compaction, so write the summary to serve as one, "
            "in bullets under Goal; State (commits with short sha, uncommitted files, where work stopped as path:line or the command); "
            "Next (the exact next action first); Watch out (unverified items, failing tests, open questions). Name exact paths and commands.")


def due_now(event, state, sfile, root, sid, tokens):
    """Tell the model a compaction is being put off for its handoff: it never sees a PreCompact block, and the deferral can start
    while no HANDOFF REQUIRED notice has fired. Said once (`told`), on the first event after a block."""
    state["told"] = True
    sfile.write_text(json.dumps(state))
    return say(event, f"HANDOFF REQUIRED: the autocompact is due now (context {tokens} tokens) and is put off until this session's handoff is saved. Run the {SKILL} skill now: write {state.get('path') or handoff_path(root, sid)} with the Write tool, check it and commit only that file (skip the commit if handoff/ is gitignored). Other tools are blocked until then.")


def main():
    data = json.load(sys.stdin)
    # A subagent's events carry its agent_id but the parent's session_id, so they would share the parent's state file: a
    # pending main thread then denied every running subagent's tools (Oct 23 2026). The guard is for the main thread only.
    if os.environ.get("HANDOFF_AT", "").strip() == "0" or data.get("agent_id"):
        return
    event, sid = data.get("hook_event_name"), data.get("session_id", "unknown")
    # The project, not the shell's folder: on Nov 14 2026 a session that had `cd`'d into a nested lab repo got a notice naming
    # <lab>/handoff/, and the guard then refused the Edit of it from the project's root. runs_own_copy uses the same variable.
    root, is_git = project_root(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
    if runs_own_copy(Path(os.environ.get("CLAUDE_PROJECT_DIR") or root)):
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    sfile = STATE_DIR / f"{sid}.json"
    state = json.loads(sfile.read_text()) if sfile.exists() else {"status": "off"}

    transcript = data.get("transcript_path", "")
    if event == "PreCompact":
        tokens, model, _, ceiling = read_transcript(transcript)
        autocompact = thresholds(model, root, ceiling)[0]
        done = state["status"] == "done" and state.get("handoff") and Path(state["handoff"]).exists()
        first = state.get("deferred_at", tokens)
        room = model_window(model) - 23_000 - tokens >= HEADROOM  # no room at a model's full window: its autocompact is 10k below the hard limit
        if (data.get("trigger") == "auto" and not done and os.environ.get("HANDOFF_DEFER", "1") != "0"
                and state.get("defers", 0) < DEFER_MAX and tokens - first < DEFER_GROWTH and room):
            now = time.time()
            if state["status"] != "pending":
                state.update(status="pending", since=now, armed=now, root=root, at=tokens or autocompact,
                             path=str(handoff_path(root, sid)))
            state.update(defers=state.get("defers", 0) + 1, deferred_at=first)
            sfile.write_text(json.dumps(state))
            print(f"handoff-guard: compaction put off ({state['defers']}/{DEFER_MAX}, {tokens - first} tokens past the first) until this session's handoff is saved", file=sys.stderr)
            sys.exit(2)  # SystemExit isn't an Exception: main's guard below lets the exit code reach Claude Code
        state["compacting"] = time.time()
        manual = data.get("trigger") != "auto"
        if done and not (manual and (data.get("custom_instructions") or "").strip()):
            print(summary_instructions(state))
        elif not done and not manual:
            state["standin"] = True  # SessionStart(compact) says the summary stands in for the handoff
            print(summary_instructions(None))
        sfile.write_text(json.dumps(state))
        return

    if event == "SessionStart":
        # PreCompact ran for this compaction (a subagent's doesn't run it), so a recent marker means it is the main thread's.
        # Delete the state first: that re-arms the guard.
        if data.get("source") == "compact" and time.time() - state.get("compacting", 0) < 900:
            sfile.unlink(missing_ok=True)
            path = state.get("handoff")
            if path and Path(path).exists():
                text = resume_text(path)
                if state.get("defers"):
                    saved = datetime.fromtimestamp(Path(path).stat().st_mtime).strftime("%H:%M:%S")
                    text += (f"\n\nThe guard saw this handoff saved at {saved} while the compaction waited for it: don't write it again, "
                             f"whatever the summary above says. It was written in a hurry, so the {SKILL} skill's step 2 checks didn't run: "
                             "run them on it now (branch, sha, paths, uncommitted files), fix the file if one fails, then carry on from its Next.")
                say(event, text)
            elif state.get("standin"):
                say(event, "The compaction ran before this session's handoff was saved; the summary above was written to stand in for it. Carry on with the task; no handoff is needed now.")
        for old in STATE_DIR.glob("*"):  # tidy state from sessions that ended
            if old.is_file() and old.stat().st_mtime < time.time() - 3 * 86400:
                old.unlink(missing_ok=True)
        return

    # One read of the transcript per event; PreToolUse reads it only while pending, the only time it acts.
    scanned = event in ("UserPromptSubmit", "PostToolUse") or (event == "PreToolUse" and state["status"] == "pending")
    tokens, model, compacted, ceiling = read_transcript(transcript) if scanned else (0, "", None, None)
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

    measure = state["status"] == "off"
    if measure and event in ("UserPromptSubmit", "PostToolUse"):
        autocompact, handoff_at, _, _ = thresholds(model, root, ceiling)
        if tokens >= handoff_at:
            now = time.time()
            path = str(handoff_path(root, sid))
            sfile.write_text(json.dumps({"status": "pending", "since": now, "armed": now, "root": root, "at": handoff_at, "path": path}))
            return say(event, f"HANDOFF REQUIRED: context is {tokens} tokens; autocompact runs at {autocompact}. Pause the current task at a safe point and run the {SKILL} skill: write exactly {path} with the Write tool (that exact suffix marks it as this session's), check it and commit only that file (skip the commit if handoff/ is gitignored). Other tools are blocked until then; afterwards carry on with the task.")

    if state["status"] == "pending" and event == "PostToolUse":
        # This session's own Write or Edit of a handoff marks that file as its own, whatever it is named.
        written = (data.get("tool_input") or {}).get("file_path")
        if data.get("tool_name") in ("Write", "Edit", "MultiEdit") and written and in_handoff_dir(root, written) and not state.get("handoff"):
            state["wrote"] = str(Path(written).resolve())
            sfile.write_text(json.dumps(state))
        local = handoff_local(root, is_git)
        path = own_handoff_since(root, local, state["since"], own_handoffs(root, sid, state))
        if path:
            state.update(status="done", handoff=path)
            state.pop("wrote", None)
            sfile.write_text(json.dumps(state))
            if local:
                prune(root)
            return say(event, f"Handoff {'saved' if local else 'committed'} ({state['handoff']}). Tools are unblocked: carry on with the task. After the autocompact the handoff is pasted back in as \"Previous context\".")
        if state.get("defers") and not state.get("told"):
            return due_now(event, state, sfile, root, sid, tokens)

    if state["status"] == "pending" and event == "UserPromptSubmit":
        if state.get("defers") and not state.get("told"):
            return due_now(event, state, sfile, root, sid, tokens)
        say(event, "Reminder: the handoff is still required; finish it before other work.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never break the session over a guard bug
        print(f"handoff-guard: {exc}", file=sys.stderr)
