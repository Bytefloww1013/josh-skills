### Pause safely

**You own a clean stop. Leave a handoff the next context can start from without the transcript.**

Pause when the user asks for a handoff, or when the handoff-guard hook prints HANDOFF REQUIRED. A handoff is not a stop: once it is saved, carry on with the task (`byte-handoff` step 4).

1. Stop at a safe point. Finish the current slice or leave its box unticked. Tick a slice `- [x]` only when it is done and its tests pass.
2. Do not commit a half-done phase. The code is committed once per phase, not per slice, and a red phase is never committed. The handoff lists the uncommitted files instead.
3. Take no irreversible step to pause. Do not push (`byte-handoff`: "Don't push"), though `docs/directives/git-and-prs.md` lets a branch be pushed without asking elsewhere. Open no PR: that needs the user's say-so (Autonomy in `SKILL.md`). A `/byte-gh-issue-claim` run does push after each green phase, as its own Step 6, not as part of a pause.
4. Write the handoff with the `byte-handoff` skill (`/byte-handoff`). When the notice names the file, write exactly that path with the Write tool. Without a notice (the user asked), the root is the session's project, not the shell's current folder, and the name has no tag: `<root>/handoff/handoff-$(date +%Y%m%d-%H%M%S).md`. Bullets only, under 30 lines and 2,500 characters. The title is `# Handoff YYYY-MM-DD HH:MM, <repo name> @ <branch> (<short HEAD sha>)`, then four sections:
   - Goal: point to the plan or spec file rather than restating it.
   - State: Done commits with what was verified, Uncommitted files, and where you Stopped at.
   - Next: step 1 is a file and the change there, or the exact command.
   - Watch out: unverified items, failing tests, traps, open questions.
   Decisions go in the plan file if there is one; the handoff holds only ones made since that are written down nowhere. Leave out empty sections. No secrets, tokens or `.env` values. No `@path`.
5. Check it against the repo, not memory. The branch and sha in its title match `git rev-parse --abbrev-ref HEAD` and `git rev-parse --short HEAD`. Every path exists. The Uncommitted lines match `git status --short`. `wc -lc <file>` is within the limit.
6. Save it. `handoff/` is gitignored here (`git check-ignore -q handoff/` succeeds), so skip the commit. The hook keeps the newest three handoffs on disk. A handoff is never committed.

**While a handoff is pending** the hook denies other tools until a file under `handoff/` is saved. A compaction that comes before the handoff is saved is put off (up to 25k tokens of growth), and the next notice names the file to write. It allows reads (Read, Grep, Glob, LS, Skill, ToolSearch, ReadNotifications and the codegraph tools), Write and Edit under `handoff/`, and shell commands whose every segment starts with `git`, `mkdir`, `date`, `ls`, `pwd`, `cat`, `head`, `tail`, `wc`, `echo`, `true`, `test`, `stat`, `grep`, or a `for` loop. A `( … )` or `{ …; }` group passes when every command inside it does, and an `rtk` prefix or a leading `NAME=value` is skipped. Of git it allows only `status`, `log`, `diff`, `add`, `commit`, `rev-parse`, `show`, `branch` and `check-ignore`. The hook's `READ_ONLY`, `SHELL_OK` and `GIT_OK` sets are the source. The hook fires on every model and ignores subagents. `HANDOFF_AT=0` switches it off. `docs/skills/byte-handoff.md` explains how to unstick a session and what to tell the user: a guard that denies a tool handoff work needs, or that fires in a subagent or at points that don't match the model's window.

**A claim run** keeps its state on disk: `temp-gh-issue<N>-implementation.md` and the notes block in `AGENTS.md`. Its Step 0 finds the plan file and the issue's branch, then gates: resume at the first unchecked slice, or start fresh (`playbooks/session-pickup.md`).

**Reply:** where you stopped, the handoff path, what is committed and what is not, and the first action on resume. This is a pause, not a final report.

Sources: CLAUDE.md, .claude/hooks/handoff-guard.py, .claude/settings.json, .claude/skills/byte-handoff/SKILL.md, docs/skills/byte-handoff.md, docs/directives/plans.md, .claude/skills/byte-gh-issue-claim/SKILL.md, .gitignore
