# Autonomy details

Use this reference when you need to know who merges, how an `--auto` gate is decided, or what the repo's hooks actually enforce. The gates themselves are in `SKILL.md` (Autonomy). Nothing here relaxes them.

## Who merges

- The owner's account merged every merged PR, release PRs included.
- GitHub's `allow_auto_merge` setting is on, but no file in the repo arms auto-merge and none calls `gh pr merge`.
- The repo has no CODEOWNERS file. Branch protection for `main` could not be read (HTTP 403).
- `docs/directives/git-and-prs.md` says PRs to `main` are squash-merged only, as a `[judgment]` rule. GitHub still allows merge commits and rebase merges.

## `--auto`

- `/byte-gh-issue-claim <N>` stops at each approval gate. With `--auto`, each gate goes to a Decision subagent instead.
- The Decision subagent never picks a `one-way-door` option.
- On `STOP` (every option is a one-way door), the run stops and asks the user.
- No decision can waive a Guardrail, because a Guardrail is the user's.

## Guardrails actually wired

`.claude/settings.json` holds hooks, the `josh-skills` marketplace (`extraKnownMarketplaces`) and the plugins it turns on (`enabledPlugins`: byte-stack and arch-skills). It has no permissions block and no env block.

- **`.claude/hooks/handoff-guard.py`** runs on SessionStart (`startup|clear|compact`), UserPromptSubmit, PreToolUse, PostToolUse (every tool) and PreCompact.
  - byte-stack registers its own copy of the guard on the same events. That copy does nothing in a project whose `.claude/settings.json` registers this file, so one guard runs.
  - On every model, it prints HANDOFF REQUIRED 35k tokens before the autocompact, which it works out from that model's window.
  - While a handoff is pending, it denies tool calls other than handoff work and allows only a short list of git subcommands. Its own comment calls the check a shortcut that checks command names only.
  - It ignores subagent events.
- **`scripts/codegraph-ensure.sh`** runs on SessionStart (`startup|resume`), async.
- **`scripts/claude-edit-hooks.ts`** runs before and after each Edit or Write.
  - Before: it refuses an edit to a generated module registry, the route tree, a reference `bun run docs:gen` writes, or a migration SQL file or snapshot already on the base branch.
  - After: it formats the edited `.ts`, `.tsx` or `.json` file with Oxfmt.
- **The `impeccable` design hook** runs on SessionStart, after each Edit or Write (it checks UI edits), and on Stop (a deeper design pass), when the skill's binary is present. `impeccable hooks off` turns it off for everyone (`docs/skills/impeccable.md`). In a cloud session, its first run downloads the binary and can time out.
- **The arch-skills plugin's hook** runs before a Bash `gh pr create` and adds a reminder to run `pr-erosion-check`. It never blocks the command ([helpers.md](helpers.md), arch-skills).
- `.claude/hooks/` holds only `handoff-guard.py`. Outside a pending handoff, no hook blocks a git command.
