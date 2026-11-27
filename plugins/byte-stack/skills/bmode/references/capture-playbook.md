# Capture a repo-specific playbook

Capture proven, repository-local procedures into `.byte-stack/` without bloating `bmode` base context or overwriting manual edits.

## Reusability gate

Skip capture silently if ANY hard disqualifier holds:
1. The run used a read-only Q&A (`investigation.md`) or meta playbook (`pause-safely.md`, `session-pickup.md`, `worktree-cleanup.md`).
2. An existing bundled or `.byte-stack/` playbook already covered the procedure with no repo-specific delta.
3. The task failed, was interrupted, or verification checks did not pass.
4. The session is outside a Git worktree, running as a `byte-agent` delegate, running non-interactively, or `.byte-stack/.no-capture-prompt` exists (or the user opted out earlier).
5. The change was a trivial one-off edit (single typo, unique incident, or one-time fix).

Prompt only when ALL three criteria hold:
1. **Repo-specific choreography:** Concrete local commands, paths, build/test/release steps, or ordering constraints absent from bundled playbooks.
2. **Repeatable class:** Likely to recur in this repository, came from a second-time correction (`principle-encode-lessons-in-structure`), or was designed as an uncovered workflow via `figure-it-out`.
3. **Verified:** At least one concrete verification check ran and passed in this session.

Prompt with one line after the task result:
`Reusable repo workflow detected (<key>): save to .byte-stack/<kind>/<key>? (y/N)`

## Extract payload

Only after the user accepts (or invokes `capture-playbook` directly), build a JSON object conforming to `references/capture-payload.schema.json` (inspect via `python3 "<bmode directory>/scripts/capture_playbook.py" schema`):

- `schema_version`: `1`
- `kind`: `"playbooks"` for top-level routed tasks (`use_when` required) or `"workflows"` for helper procedures named by another step
- `key`: lowercase kebab-case `.md` path (e.g. `release-notes.md` or `checks/preflight.md`)
- `title`: short single-line H1 title (3-80 chars)
- `use_when`: single-line routing trigger (10-200 chars; required for `playbooks`)
- `prerequisites` (optional list), `steps` (1-15 items), `verification` (1-10 items), `guardrails` (optional list)

Keep secrets, tokens, private keys, and machine-local home paths (`/home/...`, `/Users/...`, `C:\Users\...`) out of every field, and keep scalar strings single-line without `---`.

## Preview, confirm, and write

1. Always preview first with `--dry-run` (creates nothing on disk):
   ```sh
   python3 "<bmode directory>/scripts/capture_playbook.py" write --stdin --dry-run <<'EOF'
   { ... }
   EOF
   ```
2. Check the exit code and unified diff:
   - Exit `0` (`create` or `unchanged`): show the diff summary and ask for confirmation before writing.
   - Exit `3` (`conflict`): an existing file differs. Tell the user whether it is an unmodified managed file (`--update` allowed) or a hand-authored / manually edited file (`manual` or `managed-modified`), show the diff, and ask whether to update, pick a new `key`, or skip. Never pass `--force` without explicit user approval.
   - Exit `1` or `2`: fix payload validation issues or report path/Git/symlink diagnostics and stop.
3. After user confirmation, run the write command (adding `--update` only if confirmed):
   ```sh
   python3 "<bmode directory>/scripts/capture_playbook.py" write --stdin <<'EOF'
   { ... }
   EOF
   ```
4. Verify strict schema compliance and `$bmode` discovery from the worktree:
   ```sh
   python3 "<bmode directory>/scripts/capture_playbook.py" validate "<written path>"
   python3 "<bmode directory>/scripts/assets.py" list-playbooks
   python3 "<bmode directory>/scripts/assets.py" resolve "<kind>" "<key>"
   ```
