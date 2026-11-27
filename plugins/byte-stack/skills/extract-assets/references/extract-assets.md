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
- Keep secrets, tokens, private keys, and machine-local home paths (`/home/...`, `/Users/...`, `C:\Users\...`) out of every field (`payload`, `content`, `key`, `rationale`, `provenance`).

## Provenance requirements

Every candidate must cite at least one tracked, non-excluded regular file in `provenance`:

- `path`: repo-relative POSIX path from the inventory.
- `command` (optional): command snippet that appears in the cited file (whitespace-normalized).
- `key` (optional): dotted configuration key whose segments appear in the cited file.
- `line` (optional): 1-based line number within the cited file.

## Deduplication rules

`extract_assets.py write` computes a verdict for every candidate and never skips silently:

| Verdict | Meaning | Flag needed alongside `--approve <id>` |
| --- | --- | --- |
| `new` | No collision with `.byte-stack/`, bundled `bmode`, or steering files | None |
| `exists-identical` | Existing `.byte-stack/<kind>/<key>` matches byte-for-byte | None (no-op, mtime preserved) |
| `exists-differs` | Existing `.byte-stack/<kind>/<key>` differs | `--update <id>` for unmodified managed playbooks/workflows; `--force <id>` for manual/modified files and all `references/`/`scripts/` |
| `overrides-bundled` | Same `kind`/`key` as a bundled `byte-stack` asset | `--override-bundled <id>` (or `--force <id>`) |
| `restates-steering` | All provenance cites steering files, or >= 80% of lines appear verbatim in steering files | `--force <id>` |
| `duplicates-catalog` | Same normalized trigger or title as another bundled or repo catalog entry | `--force <id>` |

Soft `similar_to` warnings highlight token overlap with existing catalog entries or steering files; review them with the user before approving.

## Preview, approval, and write flow

1. Preview every candidate without touching disk:
   ```sh
   python3 "<extract-assets directory>/scripts/extract_assets.py" write --stdin --dry-run --json <<'EOF'
   { ... }
   EOF
   ```
2. Present each candidate's `id`, `category`, `provenance`, `verdict`, `reason`, `similar_to`, and unified diff.
3. Ask the user which IDs to write (and confirm any `--update`, `--override-bundled`, or `--force` flags).
4. Write only approved IDs:
   ```sh
   python3 "<extract-assets directory>/scripts/extract_assets.py" write --stdin --approve <id> --json <<'EOF'
   { ... }
   EOF
   ```
5. Check exit codes: `0` ok, `1` invalid candidates (nothing written), `2` Git/path/symlink/`bmode` diagnostic (nothing written), `3` conflict on one or more IDs (conflicting IDs skipped; diff shown).
