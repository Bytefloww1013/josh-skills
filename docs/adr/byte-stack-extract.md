# Extracting repository knowledge into `.byte-stack/`

- **Status:** Accepted
- **Date:** 2026-11-26
- **Decision type:** Type 2 (two-way door: new skill and stdlib CLI, no new persisted on-disk format or managed marker)
- **Deciders:** Repo maintainer; agent-drafted: yes
- **Scope:** `plugins/byte-stack/skills/extract-assets/**`, `tests/test_byte_stack_extract.py`, `tests/test_byte_stack_distribution.py`
- **Supersedes:** none (extends [byte-stack-assets.md](byte-stack-assets.md) and [byte-stack-capture.md](byte-stack-capture.md))

## Context and forces

`capture-playbook` records procedures after a verified `bmode` session, but repositories adopting `byte-stack` already hold repeatable choreography, conventions, rules, and helper knowledge across CI workflows, task runners, linter configs, ADRs, directives, and scripts. Mining those by hand is slow; letting an LLM scan and write `.byte-stack/` directly risks unbounded reads, secret or local-path leakage, duplicating steering files or bundled playbooks, and overwriting hand-authored assets.

Constraints inherited from [byte-stack-assets.md](byte-stack-assets.md) and [byte-stack-capture.md](byte-stack-capture.md):
1. Git and Python 3.9+ standard library only; zero repository-writing lifecycle hooks.
2. Do not alter `assets.py`, `capture_playbook.py`, or `capture-payload.schema.json`.
3. Keep `extract-assets` a two-way door by introducing no new persisted frontmatter schema, managed marker, or sidecar file for `references/` or `scripts/`.
4. Keep base skill context lean (`disable-model-invocation: true`, `allow_implicit_invocation: false`, description <= 140 chars, `bmode/SKILL.md` <= 70 lines).

## Decision

1. **Deterministic inventory / synthesis test seam:** `scripts/extract_assets.py` splits read-only repository scanning (`inventory`) from candidate validation, deduplication, preview, and writing (`write`) via a Draft 2020-12 JSON Schema (`references/extract-candidates.schema.json`, printed by `schema`).
2. **Bounded, safe scanning:** `inventory` reads tracked entries via `git ls-files -s -z`, skips symlinks (`120000`), submodules (`160000`), vendored/build directories, secret-named paths (including `.env*` on every segment and paths matching secret patterns), and machine-local files/directories (including home paths with non-ASCII user names) without opening them. Repository files and repo `.byte-stack/` catalog heads (4 KiB per Markdown file, cut at the last newline in bytes before strict UTF-8 decoding and validated via `assets.validate_key`) are opened unbuffered (`buffering=0`) so kernel reads never exceed the shared `--max-files`/`--max-bytes` budget, and unfinished lines cut by the byte cap are dropped before signal extraction. Working-tree reads go through `assets.checked()`, scripts emit one summary signal, and every byte printed to stdout or stderr passes through one output sanitizer that redacts secrets, home paths, and whole-path repository-root prefixes without corrupting tracked paths containing the root string as a substring. Broken `.byte-stack/` state becomes a JSON diagnostic rather than a crash.
3. **Reuse existing `bmode` contracts:** `extract_assets.py` locates sibling `../bmode` (or `--bmode DIR`, exiting `2` when missing), imports `assets` and `capture_playbook` with `sys.dont_write_bytecode = True`, and delegates `playbooks/` and `workflows/` writes to `capture_playbook.py write` (parsing the real write's `--json` result for final `status`, `diff`, and `written`), followed by `capture_playbook.py validate` (invoked with repo `cwd` and a repo-relative `.byte-stack/<kind>/<key>` path) and `assets.resolve` origin confirmation.
4. **No new persisted format for `references/` and `scripts/`:** `references/` and `scripts/` compare raw bytes (catching CRLF vs LF differences), validate rendered references via `assets.inspect_file` at preflight and on the staged temp file before commit, enforce `assets.checked()`, regular-file checks, stricter lowercase key validation, UTF-8 encodability, and secret + machine-local guards (reusing `capture_playbook`'s patterns plus bare/non-ASCII home-path checks), and redact sensitive lines in all emitted diffs at the single output boundary. Creates are no-clobber (`os.link` + temp unlink, falling back to exclusive `os.open(..., O_WRONLY | O_CREAT | O_EXCL, mode)` on filesystems without hard links). A forced replacement compares the target against the previewed bytes immediately before `os.replace`; a concurrent human edit landing inside that final step before the rename can be lost (the same window as `capture_playbook.py`), and `--force <id>` is the user's explicit approval to replace the file. Absent files are created; byte-identical reruns are no-ops (`unchanged`, mtime preserved); differing files exit `3` with a unified diff and require `--force <id>`.
5. **Explicit provenance, dedupe verdicts, and approval gates:** Every candidate must cite at least one tracked, non-excluded regular file. For structured file types (`package.json`, JSON, TOML/INI/CFG, Makefile/Justfile, YAML), provenance runs the same extractor as `inventory` (uncapped) so `command` and `key` citations match extracted signals (and exact line numbers when given); for other files (prose, shell, source), `command` must appear verbatim on one line bounded by start/end of line, whitespace, or quotes/backticks, and `key` is rejected in favor of `path` plus `line`. Deduplication checks existing `.byte-stack/`, bundled `bmode` catalogs, earlier accepted batch entries, and standing steering files (excluding `.claude/settings.json`, which is classified as hooks), emitting explicit verdicts (`new`, `exists-identical`, `exists-differs`, `overrides-bundled`, `restates-steering` via whole-line verbatim matching or steering-only provenance, `duplicates-catalog` via title/trigger or identical same-kind content) plus scoped `similar_to` warnings (capped at 3). Non-`dry-run` writes require explicit per-ID `--approve <id>`. An `exists-identical` no-op needs no extra flag beyond `--approve <id>`; other non-`new` verdicts require their own single-purpose per-ID flag (`--update`, `--override-bundled`, `--allow-duplicate` for `restates-steering`/`duplicates-catalog`, or `--force` for differing files only).
6. **Per-asset batch semantics:** `write` validates rendered references, rejects ancestor/descendant target collisions among selected plans, and dry-runs every approved ID first; any preflight exit `1` or `2` writes nothing. During execution, exit `3` conflicts (including late capture conflicts and pre-rename target modifications) skip only the conflicting ID and preserve structured per-ID results. Writes are atomic per file, not transactional across multiple assets: an unexpected I/O error mid-run can leave earlier files written on disk.

## Boundary connascence

| # | Crossing elements | Type | Locality | Degree | Verdict | Guard / Fix |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `inventory` JSON -> agent synthesis -> `write` candidates JSON | Name + Type | Cross-process | 2 | OK | Draft 2020-12 `extract-candidates.schema.json` (`additionalProperties: false`) + stdlib validator |
| 2 | `extract_assets.py` -> `bmode/scripts/assets.py` & `capture_playbook.py` | Name + Algorithm | Sibling skills | 2 | OK | `--bmode` contract, exit `2` when absent, subprocess calls to `capture_playbook.py` |
| 3 | Safety patterns (`LOCAL_PATH_PATTERNS`, `SECRET_PATTERNS`) | Value | Sibling scripts | 2 | Fixed | Imported directly from `capture_playbook.py` (extended with bare home-path checks in `extract_assets.py`) |

## Fitness functions

| ID | Invariant | Check | Runs in |
| --- | --- | --- | --- |
| `FF-EXT-1` | Inventory classification, exclusions, bounded reads, determinism, root absence, broken `.byte-stack` diagnostics | `python3 -I tests/test_byte_stack_extract.py` | Local |
| `FF-EXT-2` | Provenance checks, all 3 dedupe sources, symlink/secret/local-path guards, `--dry-run`, approval gates, idempotency, manual-edit protection | `python3 -I tests/test_byte_stack_extract.py` | Local |
| `FF-EXT-3` | Packaging, manifests (`2.2.0`), zero hooks, forbidden terms, Antigravity/Codex/Claude installs | `python3 tests/test_byte_stack_distribution.py && python3 tests/test_antigravity_plugin_install.py` | Local |
| `FF-EXT-4` | Existing asset and capture contracts unchanged | `python3 tests/test_byte_stack_assets.py && python3 tests/test_byte_stack_capture.py` | Local |

## Revisit when

- Teams need multi-file atomic transactions across paired `.byte-stack/` assets (aligned with the revisit trigger in [byte-stack-capture.md](byte-stack-capture.md)).
- Real usage shows `references/` or `scripts/` require clean automated updates distinct from `--force`, justifying a persisted managed-file convention.
