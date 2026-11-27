# Synthesizing `.byte-stack/` asset candidates

Use the deterministic output of `scripts/extract_assets.py inventory` to propose high-value, repository-specific `.byte-stack/` assets without duplicating existing catalogs or steering files.

## Category-to-asset mapping

| Category | Target `kind` | What belongs here |
| --- | --- | --- |
| `workflow` | `playbooks/` or `workflows/` | Multi-step repo procedures discovered in CI pipelines, Makefiles, package scripts, or release/check scripts. Use `playbooks/` for top-level routed tasks (`use_when` required) and `workflows/` for reusable sub-procedures. |
| `convention` | `references/` | Code style, naming, formatting, linter, typechecker, and architecture conventions distilled from configs, ADRs, and directives. |
| `rule` | `references/` (or `playbooks/`/`workflows/` when procedural) | Git, branching, commit, hook, review, and repository process rules not already enforced silently by steering files. |
| `knowledge` | `references/` or `scripts/` | Reusable subsystem notes, checklists, or small self-contained helper scripts (`executable: true` when directly runnable). |

## Candidate envelope rules

Build a JSON document matching `references/extract-candidates.schema.json` (`extract_assets.py schema`):

- Top level: `{"schema_version": 1, "candidates": [...]}`.
- Every candidate has `id` equal to `"<kind>/<key>"`, `category`, `kind`, `key`, at least one `provenance` entry, and an optional `rationale`.
- `playbooks` and `workflows` carry `payload` (the `capture_playbook.py` fields minus `schema_version`, `kind`, and `key`: `title`, `steps`, `verification`, optional `prerequisites`/`guardrails`, and required `use_when` for `playbooks`). Keys must be lowercase kebab-case ending in `.md`.
- `references` carry LF Markdown `content` (max 64 KiB) with a lowercase kebab-case `.md` key.
- `scripts` carry LF `content` (max 64 KiB) with a lowercase key (optional extension) and optional `executable: true`.
- Keep secrets, tokens, private keys, and machine-local home paths (`C:\Users\<user>`, or an absolute path with a `home/<user>` or `Users/<user>` segment at any depth, such as `/home/<user>`, `/var/home/<user>` or `/mnt/c/Users/<user>`; non-ASCII user names and paths without a trailing slash count) out of every field (`payload`, `content`, `key`, `rationale`, `provenance`). An absolute route such as `/home/about` reads as a home path and is rejected: write it another way. A CI runner home such as `/home/runner/work` counts too. An `http` or `https` URL with a host is not checked for such segments, for all four kinds. All strings must be valid UTF-8 (no lone surrogates).

## Provenance requirements

Every candidate must cite at least one tracked, non-excluded regular file in `provenance`:

- `path`: repo-relative POSIX path from the inventory.
- `command` (optional): for structured files (`package.json`, JSON, TOML/INI/CFG, Makefile/Justfile, YAML workflows/hooks), must equal an extracted `command` signal as printed by `inventory` (whitespace-normalized; supports `\` continuations and Make recipe prefix stripping). For other files (prose, shell, source), must appear verbatim on one line (supporting `\` continuations), bounded by start/end of line, whitespace, or quotes/backticks on both sides.
- `key` (optional): for structured files, must equal an extracted `key` signal as printed by `inventory` (e.g. `scripts.<name>`, `tool.ruff.line-length`, `hooks.PreToolUse`). Not supported on prose, shell, or source files (cite `path` and `line` instead).
- `line` (optional): 1-based line number within the cited file; when combined with `command` or `key`, it must equal that extracted signal's line (or the matching line in non-structured files).

## Deduplication rules

`extract_assets.py write` computes a verdict for every candidate and never skips silently:

| Verdict | Meaning | Flag needed alongside `--approve <id>` |
| --- | --- | --- |
| `new` | No collision with `.byte-stack/`, bundled `bmode`, or steering files | None |
| `exists-identical` | Existing `.byte-stack/<kind>/<key>` matches byte-for-byte | None (no-op, mtime preserved) |
| `exists-differs` | Existing `.byte-stack/<kind>/<key>` differs (including CRLF vs LF bytes on `references/` and `scripts/`) | `--update <id>` for unmodified managed playbooks/workflows; `--force <id>` for manual/modified files and all `references/`/`scripts/` |
| `overrides-bundled` | Same `kind`/`key` as a bundled `byte-stack` asset | `--override-bundled <id>` |
| `restates-steering` | All provenance cites steering files (`.claude/settings.json` is classified as hooks, not steering), or >= 80% of lines appear verbatim (whole-line match) in steering files | `--allow-duplicate <id>` |
| `duplicates-catalog` | Same normalized trigger or title, or byte-identical same-kind content, as another bundled, repo, or earlier accepted batch entry | `--allow-duplicate <id>` |

Flags are single-purpose: `--force <id>` authorizes replacing a differing file only and never bypasses `restates-steering`, `duplicates-catalog`, or `overrides-bundled`. When a candidate both differs from an existing file and triggers a dedupe block, preview reports both conflicts and the diff, and writing requires both flags.

Soft `similar_to` warnings (capped at 3) compare playbooks/workflows against playbook/workflow titles and triggers, references against reference titles, and non-script candidates against steering files (including bullet-normalized line overlap). Scripts emit no `similar_to` noise.

A file record with `"signals_withheld": N` had N signals left out because they hold a secret, a home path or the repository root; cite such a line with `path` plus `line`, without its text.

A repo catalog entry in the inventory with `"truncated": true` was listed from the first 4 KiB of its file only. Run `assets.py resolve <kind> <key>` before you rely on it; the resolver reads the whole file.

## Preview, approval, and write flow

1. Run `inventory` (compact JSON by default; pass `--pretty` for indented output; script files emit at most one comment/docstring summary signal).
2. Preview every candidate without touching disk:
   ```sh
   python3 "<extract-assets directory>/scripts/extract_assets.py" write --stdin --dry-run --json <<'EOF'
   { ... }
   EOF
   ```
   All CLI output (stdout JSON, text mode, diffs, and stderr diagnostics) passes through one output sanitizer that redacts secrets, home paths, and whole-path repository-root prefixes. Invalid references (e.g., conflicting frontmatter/body triggers) and ancestor/descendant target collisions fail at preflight before any file is written.
3. Present each candidate's `id`, `category`, `provenance`, `verdict`, `reason`, `similar_to`, and unified diff.
4. Ask the user which IDs to write (and confirm any `--update`, `--override-bundled`, `--allow-duplicate`, or `--force` flags).
5. Write only approved IDs:
   ```sh
   python3 "<extract-assets directory>/scripts/extract_assets.py" write --stdin --approve <id> --json <<'EOF'
   { ... }
   EOF
   ```
   Creates are no-clobber (`os.link`, falling back to exclusive `O_CREAT | O_EXCL` on filesystems without hard links). A forced replacement compares the target with the previewed bytes immediately before `os.replace`; a concurrent edit landing inside that last step before the rename can be lost (the same window as `capture_playbook.py`), and `--force <id>` is the user's approval to replace the file. Writes are atomic per file; an unexpected I/O error mid-run can leave earlier files written.
6. Check exit codes: `0` ok, `1` invalid candidates or colliding targets (nothing written), `2` Git/path/symlink/`bmode` diagnostic (nothing written on preflight failure), `3` conflict on one or more IDs (conflicting IDs skipped; diff shown).
