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
2. **Bounded, safe scanning:** `inventory` reads tracked entries via `git ls-files -s -z`, skips symlinks (`120000`), submodules (`160000`), vendored/build directories, secret-named files, and machine-local files without opening them, enforces `--max-files` and `--max-bytes`, checks working-tree reads through `assets.checked()`, drops sensitive signal lines, and emits deterministic sorted JSON containing no timestamps, absolute paths, or repo-root strings. Broken `.byte-stack/` state becomes a JSON diagnostic rather than a crash.
3. **Reuse existing `bmode` contracts:** `extract_assets.py` locates sibling `../bmode` (or `--bmode DIR`, exiting `2` when missing), imports `assets` and `capture_playbook` with `sys.dont_write_bytecode = True`, and delegates `playbooks/` and `workflows/` writes to `capture_playbook.py write` followed by `capture_playbook.py validate` and `assets.resolve` origin confirmation.
4. **No new persisted format for `references/` and `scripts/`:** `references/` and `scripts/` use an atomic `tempfile` + `os.replace` writer with `assets.checked()`, regular-file checks, stricter lowercase key validation, and `capture_playbook`'s `LOCAL_PATH_PATTERNS` and `SECRET_PATTERNS`. Absent files are created; byte-identical reruns are no-ops (`unchanged`, mtime preserved); differing files exit `3` with a unified diff and require `--force <id>`.
5. **Explicit provenance, dedupe verdicts, and approval gates:** Every candidate must cite at least one tracked, non-excluded regular file (`path`, optional `command`/`key`/`line`). Deduplication checks existing `.byte-stack/`, bundled `bmode` catalogs, and standing steering files, emitting explicit verdicts (`new`, `exists-identical`, `exists-differs`, `overrides-bundled`, `restates-steering`, `duplicates-catalog`) plus soft `similar_to` warnings. Non-`dry-run` writes require explicit per-ID `--approve <id>`, and non-`new` verdicts require their own per-ID flag (`--update`, `--override-bundled`, or `--force`).
6. **Per-asset batch semantics:** `write` dry-runs every approved ID first; any exit `1` or `2` writes nothing. During execution, exit `3` conflicts skip only the conflicting ID. Writes are atomic per file (`os.replace`), not transactional across multiple assets.

## Boundary connascence

| # | Crossing elements | Type | Locality | Degree | Verdict | Guard / Fix |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `inventory` JSON -> agent synthesis -> `write` candidates JSON | Name + Type | Cross-process | 2 | OK | Draft 2020-12 `extract-candidates.schema.json` (`additionalProperties: false`) + stdlib validator |
| 2 | `extract_assets.py` -> `bmode/scripts/assets.py` & `capture_playbook.py` | Name + Algorithm | Sibling skills | 2 | OK | `--bmode` contract, exit `2` when absent, subprocess calls to `capture_playbook.py` |
| 3 | Safety patterns (`LOCAL_PATH_PATTERNS`, `SECRET_PATTERNS`) | Value | Sibling scripts | 2 | Fixed | Imported directly from `capture_playbook.py` instead of duplicated |

## Fitness functions

| ID | Invariant | Check | Runs in |
| --- | --- | --- | --- |
| `FF-EXT-1` | Inventory classification, exclusions, bounded reads, determinism, root absence, broken `.byte-stack` diagnostics | `python3 -I tests/test_byte_stack_extract.py` | Local + CI |
| `FF-EXT-2` | Provenance checks, all 3 dedupe sources, symlink/secret/local-path guards, `--dry-run`, approval gates, idempotency, manual-edit protection | `python3 -I tests/test_byte_stack_extract.py` | Local + CI |
| `FF-EXT-3` | Packaging, manifests (`2.2.0`), zero hooks, forbidden terms, Antigravity/Codex/Claude installs | `python3 tests/test_byte_stack_distribution.py && python3 tests/test_antigravity_plugin_install.py` | Local + CI |
| `FF-EXT-4` | Existing asset and capture contracts unchanged | `python3 tests/test_byte_stack_assets.py && python3 tests/test_byte_stack_capture.py` | Local + CI |

## Revisit when

- Teams need multi-file atomic transactions across paired `.byte-stack/` assets (aligned with the revisit trigger in [byte-stack-capture.md](byte-stack-capture.md)).
- Real usage shows `references/` or `scripts/` require clean automated updates distinct from `--force`, justifying a persisted managed-file convention.
