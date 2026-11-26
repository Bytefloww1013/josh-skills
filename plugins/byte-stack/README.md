# byte-stack

`bmode` for `bphs-connect`, its playbooks and principle skills, helper skills (`how`, `architect`, `blast-radius`, `figure-it-out`, `council-review`, `docs-add`, `docs-review`, `gen-issue`, `sharpen`, `sol-loop`, `technical-writing`, `typescript-best-practices`, `unslop`), the `byte-agent` delegate subagent, and `byte-handoff` with its Claude Code handoff-guard hook.

## Install

### Claude Code

```
claude plugin marketplace add Bytefloww1013/josh-skills
claude plugin install byte-stack@josh-skills --scope user
```

### Antigravity

```
agy plugin install /path/to/josh-skills/plugins/byte-stack
```

`byte-stack` ships `.claude-plugin/plugin.json` for Claude Code and `.antigravity-plugin/plugin.json` for Antigravity, so each harness loads the metadata and hooks it supports with no patching after the install. Only the Antigravity manifest has a `version`. Claude Code takes the version of a plugin without one from the commit, so every push to `main` is an update; a `version` in `.claude-plugin/plugin.json` would pin the plugin until the number changed. Bump the Antigravity `version` when a change should reach Antigravity installs.

## Subagent (`byte-agent`)

`agents/byte-agent.md` sets `subagent: true` and `mainAgent: false` so Antigravity exposes it for background delegation without listing it as a primary session agent, while Claude Code ignores those extra frontmatter keys. It omits `tools:` so both harnesses inherit their own full toolset (a single `tools:` allowlist cannot name both Claude Code and Antigravity tools). When no parent path is passed, the prompt searches Antigravity (`$GEMINI_HOME/config/plugins/`, `~/.gemini/config/plugins/`, `.agents/plugins/`) and Claude Code (`~/.claude/plugins/`) plugin folders for `skills/bmode/SKILL.md`.

## Handoff-guard hooks and harness support

- **Claude Code:** loads `hooks/hooks.json`, which wires `hooks/handoff-guard.py` to `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, and `PreCompact`.
- **Antigravity:** registers no handoff-guard hooks. It reads plugin hooks only from a `hooks.json` at the plugin root, and byte-stack has none. `agy plugin validate --strict` warns that `hooks/hooks.json` is never loaded; that warning is expected.
  - `PreCompact` and `UserPromptSubmit` are unsupported in Antigravity (those events do not exist).
  - `SessionStart`, `PreToolUse`, and `PostToolUse` exist in Antigravity, but `hooks/handoff-guard.py` is unverified under Antigravity (it reads Claude Code JSONL transcripts, Claude autocompact settings, and snake_case hook payloads, and returns Claude Code `hookSpecificOutput` JSON), so none of those events are enabled on Antigravity.

The `byte-handoff` skill itself installs on both harnesses for manual handoffs.

## Tests

- Handoff guard (Claude Code): `python3 plugins/byte-stack/hooks/check-handoff-guard.py`
- Antigravity install smoke test (isolated `HOME` and config; requires `agy` on `PATH`, exits `2` when missing): `python3 tests/test_antigravity_plugin_install.py`
