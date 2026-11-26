# arch-skills

Six skills that help a coding agent keep a codebase sound. The first four share one library of principles (connascence, coupling metrics, erosion vectors, contracts, fitness functions, severity) and a project profile for bphs-connect.

| Skill | Use it when |
|---|---|
| `arch-skills:architecture-decision-review` | You must choose between design options before you build. Output: options, connascence table, decision, ADR. |
| `arch-skills:pr-erosion-check` | A PR or branch is ready for review, or an agent says it is done. Output: merge verdict with file:line findings, including scope against the linked issue. |
| `arch-skills:architecture-review-report` | You have a plan, spec, RFC or GitHub issues to review. Output: element-by-element report with severity and cited principle. |
| `arch-skills:repo-navigability-audit` | You want to know how easily an agent or a new person finds their way in a repo. Output: scored audit with fixes. |
| `arch-skills:state-machine-audit` | You want the implicit state machines in an app found, mapped and checked for paths to invalid states. Output: findings report with Mermaid diagrams. Read-only. |
| `arch-skills:user-flow-mapper` | You want a user's journey for one task mapped. Output: Mermaid diagrams for approval, then mockups, a clickable prototype and a UX report. |

Claude loads a skill by itself when the task fits its description. You can also call one by name, for example `/arch-skills:pr-erosion-check 41`.

## Install

### Claude Code

```
claude plugin marketplace add Bytefloww1013/josh-skills
claude plugin install arch-skills@josh-skills
```

To try it without installing, from the josh-skills root: `claude --plugin-dir plugins/arch-skills`.

### Antigravity

```
agy plugin install /path/to/josh-skills/plugins/arch-skills
```

The plugin installs on Antigravity as it is: `.antigravity-plugin/plugin.json` is its manifest and `hooks.json` at the plugin root holds its Antigravity hooks. Antigravity never loads `hooks/hooks.json` (Claude Code's hooks), and `agy plugin validate` warns about that file. Keep the version in `.claude-plugin/plugin.json` and `.antigravity-plugin/plugin.json` the same.

The scripts need Python 3 (standard library only). `pr-erosion-check` uses `git` and, for PRs, `gh`.

## The hook

`hooks/pre_pr_reminder.py` reminds the agent to run `pr-erosion-check` when it is about to run `gh pr create`. It never blocks the command.

- Claude Code: `hooks/hooks.json` runs it as a `PreToolUse` hook. It answers with `hookSpecificOutput.additionalContext`, and with empty stdout when no reminder applies.
- Antigravity: the root `hooks.json` runs it as a `PreToolUse(run_command)` hook and as a `PreInvocation` hook. Antigravity does not pass `reason` to the model when the decision is `allow`, so the `PreToolUse` call answers a plain `{"decision": "allow"}` and keeps the reminder in a file named after the conversation, under `$PLUGIN_DATA/pending-pr-reminders/` (the temp folder when `PLUGIN_DATA` is unset). Before the model's next call, the `PreInvocation` call sends it once as a system message and deletes the file; it also deletes kept reminders older than a day. When the reminder can't be kept (no `conversationId`, or the folder can't be written), the `PreToolUse` call answers `{"decision": "allow", "reason": ...}` instead.

In both harnesses it leaves the reminder out when every file the branch changes against the PR's base is a doc file (`.md`, `.mdx`, `.markdown`, `.txt`, `.rst`, `.adoc`), keeps the reminder on code-to-doc renames, and shows it whenever git can't tell.

To turn it off, delete `hooks/hooks.json` (Claude Code) or the root `hooks.json` (Antigravity), or disable the plugin's hooks in your settings.

## Tests

- PR reminder hook (Claude Code and Antigravity payloads): `python3 plugins/arch-skills/hooks/test_pre_pr_reminder.py`
- Erosion scan scripts: `python3 plugins/arch-skills/skills/pr-erosion-check/scripts/test_erosion_scan.py`
- Shared reference copies: `plugins/arch-skills/check-copies.sh`
- Antigravity install smoke test (isolated `HOME` and config; requires `agy` on `PATH`, exits `2` when missing): `python3 tests/test_antigravity_plugin_install.py`

## Editing

Edit the skills here, in `skills/<name>/`. There is no build step.

Each skill carries its own copy of the reference files and scripts it shares with the others, so it works when installed alone. `severity.md`, `fitness-functions.md` and `project-bphs-connect.md` are in all four review skills, and other files in two or three. `state-machine-audit` and `user-flow-mapper` share no files. When you change a shared file, change every copy, then run `plugins/arch-skills/check-copies.sh`. It names each file whose copies differ and exits 1 if any do.
