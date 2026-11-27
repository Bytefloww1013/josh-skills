# Byte Stack

Run **bmode** to route a task to an engineering playbook. The plugin also includes engineering principles, documentation and review helpers, and a session handoff skill. Git and Python 3.9+ are required for asset lookup and initialization. Repositories can use the bundled playbooks immediately.

## Install

| Host | Install | Invoke |
| --- | --- | --- |
| Claude Code | `claude plugin marketplace add Bytefloww1013/josh-skills`, then `claude plugin install byte-stack@josh-skills` | `/byte-stack:bmode`, `/byte-stack:capture-playbook`, `/byte-stack:extract-assets`, and `/byte-stack:init` |
| Antigravity CLI | `agy plugin install /path/to/josh-skills/plugins/byte-stack` | Select `bmode`, `capture-playbook`, `extract-assets`, or `init` from `/skills`. |
| Codex CLI | `codex plugin marketplace add /path/to/josh-skills`, then `codex plugin add byte-stack@josh-skills` | Select `$byte-stack:bmode`, `$byte-stack:capture-playbook`, `$byte-stack:extract-assets`, or `$byte-stack:init` from the skill picker. Codex also exposes init as the plugin's onboarding skill on supported clients. |
| Individual skills | `npx skills add Bytefloww1013/josh-skills --skill bmode` | Select the installed skill. Add init separately to scaffold a checkout. |

For a branch under development, use its absolute checkout path in either marketplace add command. Start or reload the host session after installation as required. In each target repository run init explicitly to create tracked placeholders for the four asset directories. Repeating init preserves user files. No installation or session hook scaffolds a repository.

## Add a repository playbook

After running init, create `.byte-stack/playbooks/release-notes.md`:

```markdown
# Release notes

Use when: Prepare release notes for a tagged version.

Identify the previous tag, read the intervening commits, and group user-visible changes by feature or fix. Cite the commits.
```

Ask bmode to run `release-notes.md`, or describe the task. Add `.byte-stack/playbooks/investigation.md` to replace the bundled investigation. A same-key override can inherit the bundled trigger. Give a new playbook its own `Use when: ` line for automatic routing.

| Kind | Use |
| --- | --- |
| `playbooks/` | Task entry points with routing descriptions |
| `workflows/` | Reusable procedures named by a step |
| `references/` | Criteria, documentation and brief templates |
| `scripts/` | Commands selected by an authorized step |

Lookup uses the current worktree root, including in a subdirectory or linked worktree. A missing local key falls through to the installed skill. Without a Git checkout, lookup uses the bundle. An invalid local override produces a diagnostic. Asset discovery reads filenames and Markdown descriptions; selecting a script never runs it. Only use scripts from a trusted checkout and apply the normal host permissions.

From the target checkout, inspect requests using the script in the **installed** bmode skill:

```sh
python3 "<bmode directory>/scripts/assets.py" list-playbooks
python3 "<bmode directory>/scripts/assets.py" resolve playbooks investigation.md
python3 "<bmode directory>/scripts/assets.py" resolve workflows pre-review.md
python3 "<bmode directory>/scripts/assets.py" --owner "<docs-review directory>" resolve references criteria.md
```

The final example checks `.byte-stack/references/docs-review/criteria.md`, then `references/criteria.md` in docs-review. Its criteria are optional. Bmode's own keys are unprefixed. New workflows, references and scripts become reachable when a playbook or skill names them. Host, user and checkout rules apply to every asset.

## Capture a verified workflow

During a `bmode` run, if a verified task uncovers repeatable repo-specific choreography not covered by an existing playbook, `bmode` offers a single-line `y/N` prompt to save it into `.byte-stack/playbooks/` or `.byte-stack/workflows/`. Create `.byte-stack/.no-capture-prompt` to disable automatic prompts in a repository. You can also invoke `capture-playbook` explicitly after a verified run.

Captured files use flat YAML frontmatter (`schema-version: 1`, `kind`, `key`, `use-when`, `managed-by`, `content-sha256`), which `assets.py` reads alongside legacy `Use when: ` lines. From the target checkout, preview, write, and validate using the deterministic CLI inside the installed `bmode` skill:

```sh
python3 "<bmode directory>/scripts/capture_playbook.py" write --stdin --dry-run < payload.json
python3 "<bmode directory>/scripts/capture_playbook.py" write --stdin < payload.json
python3 "<bmode directory>/scripts/capture_playbook.py" validate .byte-stack/playbooks/release-notes.md
```

Repeat identical runs are no-ops (`unchanged`). Clean updates to unmodified generated files require `--update`. Manually edited or hand-authored files exit `3` with a diff unless `--force` is passed explicitly. See the [capture decision](../../docs/adr/byte-stack-capture.md).

## Extract repository assets

Invoke `extract-assets` to scan the calling Git worktree and propose `.byte-stack/` assets (`playbooks/`, `workflows/`, `references/`, and `scripts/`) from CI pipelines, task runners, scripts, steering files, ADRs, directives, quality configs, and Git hooks.

The skill separates read-only scanning (`inventory`) from validated previews and writes (`write`) via a JSON Schema (`schema`). From the target checkout:

```sh
python3 "<extract-assets directory>/scripts/extract_assets.py" inventory
python3 "<extract-assets directory>/scripts/extract_assets.py" schema
python3 "<extract-assets directory>/scripts/extract_assets.py" write --stdin --dry-run --json < candidates.json
python3 "<extract-assets directory>/scripts/extract_assets.py" write --stdin --approve playbooks/release-notes.md --json < candidates.json
```

`inventory` skips symlinks, submodules, vendored/build directories, secret-named files, and machine-local files/directories without reading them, walks `.byte-stack/` under the same exclusions and `--max-files`/`--max-bytes` budget, and prints compact sorted JSON by default (`--pretty` for indented output). `write` checks tracked provenance, deduplicates against bundled `byte-stack` catalogs, existing `.byte-stack/` files, earlier batch entries, and steering files, delegates `playbooks/` and `workflows/` to `capture_playbook.py`, and writes `references/` and `scripts/` atomically without adding managed markers. Non-`dry-run` writes require explicit per-ID `--approve <id>`. An `exists-identical` rerun is a no-op (mtime preserved) and needs no extra flag beyond `--approve <id>`; other non-`new` verdicts require `--update`, `--override-bundled`, or `--force`. Writes are per-file atomic; an unexpected I/O error mid-run can leave earlier files written. See the [extract decision](../../docs/adr/byte-stack-extract.md).

## Host differences

Claude Code loads the byte-agent delegate and its handoff guard. Antigravity exposes byte-agent for delegation. Codex skills use the host's available delegation mechanism and pass the worktree and installed skill path in the brief. All hosts can invoke byte-handoff manually. Automatic handoff uses Claude Code's transcript, compaction settings and hook response format and is registered only on that host.

The guard uses the supplied context limit (`CLAUDE_CODE_MAX_CONTEXT_TOKENS` or `HANDOFF_WINDOW`), an explicit extended-context suffix, or a conservative 200,000-token estimate. It respects the host's extended-context opt-out and configured compaction threshold. Without window information it can notify early on large sessions and allows compaction to proceed. A checkout with its own registered guard continues to use that copy.

The pre-push review skill is `review-loop`. Delegation inherits the host default or honors a supported user or repo selection. Council review can use independent reviewers on the same provider.

## Package maintenance

Claude Code derives the version from Git. Antigravity and Codex use explicit manifest versions. Keep the three skill sets in one source directory. Codex declares its own hook list to prevent discovery of the Claude Code hooks. See [Codex plugin packaging](https://developers.openai.com/plugins/build/plugins) and the [asset discovery decision](../../docs/adr/byte-stack-assets.md).

Run `python3 tests/test_byte_stack_distribution.py`, `python3 tests/test_byte_stack_assets.py`, `python3 tests/test_byte_stack_capture.py`, `python3 -I tests/test_byte_stack_extract.py`, `python3 plugins/byte-stack/hooks/check-handoff-guard.py`, and `python3 tests/test_antigravity_plugin_install.py` from the source checkout.

For an opt-in end-to-end check, run `python3 tests/check_byte_stack_claude_live.py` with a signed-in Claude Code CLI. It uses four model turns, installs into a temporary profile, and verifies tool results for both playbook origins and two init runs.
