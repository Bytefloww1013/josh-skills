---
name: byte-handoff
description: Write a short, bullet-only handoff of the current work to ./handoff/handoff-<timestamp>.md at the repo root and commit it (unless handoff/ is gitignored), so the context after the autocompact (33k below the session model's /autocompact window: ~302k at 335000) can pick up from it. Use when a HANDOFF REQUIRED or HANDOFF UPDATE REQUIRED notice appears, when context is nearly full, or when the user asks for a handoff.
---

# byte-handoff

The next context starts from this file plus the repo, so it only needs what the repo can't tell it. Keep it under 30 lines and 2,500 characters. Spend no time re-reading code; write from what you already know.

## 1. Write the file

The root is `git rev-parse --show-toplevel`, or the working directory outside git. Run `mkdir -p <root>/handoff`, then write `<root>/handoff/handoff-$(date +%Y%m%d-%H%M%S).md`:

```markdown
# Handoff YYYY-MM-DD HH:MM, <repo name> @ <branch> (<short HEAD sha>)

## Goal
- One or two lines. Point to the plan or spec file rather than restating it.

## State
- Done: commits (sha) and what was verified, one line each.
- Uncommitted: `path`: a few words on what changed. One line per file.
- Stopped at: `path:line` or the command that was running.

## Next
1. The concrete next action: a file and what to do there, or the exact command.
2. The rest, one line each.

## Watch out
- Unverified items, failing tests (the error line only), traps, open questions.
```

Style rules:
- Bullets only, one line each. No prose paragraphs, no filler, no restating the user's rules or CLAUDE.md.
- Facts, not explanations. Name a file and let the next context read it: `path` or `path:line`, never a summary of its contents, signatures or helper lists.
- Don't use `@path`: it either does nothing or inlines the whole file. A plain path costs nothing until it's read.
- Decisions go in the plan file if there is one; here, only ones made since that aren't written down anywhere.
- Leave out empty sections. Never paste secrets, tokens or `.env` values.

## 2. Check it before committing

The handoff must be accurate and actionable. Check it against the repo, not memory, and fix the file until every check passes:
- The branch and sha in the title match `git rev-parse --abbrev-ref HEAD` and `git rev-parse --short HEAD`.
- Every path it names exists (`test -e <path>`), unless it says the file is to be created.
- The "Uncommitted" files match `git status --short`, apart from the handoff itself.
- Step 1 of "Next" can be started without the transcript: a file and what to change there, or the exact command to run.
- Anything unverified, failing or still open is listed under "Watch out", not hidden.
- It is under 30 lines and 2,500 characters (`wc -lc <file>`), or 36 lines and 3,000 after the step 5 update. Cut detail the repo already holds before cutting facts.

## 3. Commit only that file

Commit only after the check passes. In a git repo, commit the handoff alone, leaving the user's other staged or unstaged changes untouched:

```bash
git add -- handoff/<file> && git commit -m "docs: handoff <timestamp>" -m "Co-Authored-By: <the attribution line this session uses>" -- handoff/<file>
```

Confirm it landed with `git log -1 --stat`. Skip the commit outside git, and where `handoff/` is gitignored (`git check-ignore -q handoff/` succeeds): there the saved file is enough, and the hook keeps only the newest three handoffs on disk. Don't push.

## 4. Carry on

After the commit, say in one line which handoff was written, then go back to the task. The handoff-guard hook that sent the notice (the byte-stack plugin's `hooks/handoff-guard.py`, or the project's copy at `.claude/hooks/handoff-guard.py`; its docstring explains it) blocks other tools only until the handoff is committed (or saved, where step 3 skips the commit). When the autocompact runs (the session model's window set by /autocompact minus the 33k "Autocompact buffer" in the /context panel: ~302k at 335000), it pastes this handoff into the compacted context as "Previous context", next to the compact summary.

## 5. Update it 6k before the autocompact

If a HANDOFF UPDATE REQUIRED notice appears, the context reached the update point (6k before the autocompact: 296k with a 335000 window) without compacting, so the handoff is behind. Don't write a new file. Append to the same handoff:

```markdown
## Since the handoff
- At most 5 one-line bullets: what changed (path, sha), how it was verified, where it stands now.
```

Same style rules; no notes on what you read. If the earlier "Next" or "Watch out" are now wrong (a step is done, a new problem turned up), fix them in place too. Run the step 2 checks on what you added, then commit only that file, as in step 3 (`docs: handoff <timestamp> update`). Then carry on with the task. This happens at most once per handoff.
