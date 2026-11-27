# Capturing repo-specific playbooks into `.byte-stack/`

- **Status:** Accepted
- **Date:** 2026-11-26
- **Decision type:** Type 1 (persisted `.byte-stack/` frontmatter schema & integrity hash contract); Type 2 (trigger UX & skill packaging)
- **Deciders:** Repo maintainer; agent-drafted: yes
- **Scope:** `plugins/byte-stack/skills/bmode/**`, `plugins/byte-stack/skills/capture-playbook/**`, `tests/test_byte_stack_*.py`
- **Supersedes:** none (extends [byte-stack-assets.md](byte-stack-assets.md))

## Context and forces

Teams using `byte-stack` across repositories repeatedly rediscover local workflows (release procedures, migration checks, custom test choreography), yet `.byte-stack/playbooks/` stays empty because authoring boilerplate by hand after finishing work creates friction.

Constraints from [byte-stack-assets.md](byte-stack-assets.md) and the distribution test suite:
1. Runtime tooling stays strictly on Git and the Python 3.9+ standard library (no PyYAML or third-party `jsonschema` runtime dependency).
2. No repository-writing lifecycle hooks; Antigravity and Codex ship zero `byte-stack` hooks.
3. Selective `bmode` installs (`npx skills add Bytefloww1013/josh-skills --skill bmode`) remain self-contained inside `skills/bmode/`.
4. Captured files live in user repositories where humans edit them manually; those edits must never be silently overwritten.
5. `bmode/SKILL.md` base context and Antigravity's skill-description budget must remain minimal.

## Strategy trade-off table

| Strategy | Token cost | Maintainability | Caller friction | Host portability | Verdict |
| --- | --- | --- | --- | --- | --- |
| **1. Post-task opt-in prompt + deterministic CLI scaffolder (Chosen)** | Low (~4 lines in `bmode/SKILL.md`; schema/guide loaded only on opt-in) | High (stdlib Python CLI in `bmode/scripts/`; zero hooks; unit-testable seam) | Low (single-line `y/N` nudge only when reusability gate passes) | Full (Claude Code, Antigravity, Codex, selective `bmode`) | **Chosen** |
| **2. Explicit promotion command only** | Very low in `bmode`; small global skill index entry | High (shares same CLI scaffolder) | Medium-high (caller must remember to invoke it after every qualifying run) | Full for plugin installs | **Folded in** as thin `capture-playbook` skill calling Strategy 1's CLI |
| **3. Passive candidate detection (history mining)** | Medium-high bursts from transcript scanning & clustering | Low (private host-specific transcript formats; needs hooks/daemons) | Medium (delayed out-of-context proposals) | Poor (Claude-specific without custom adapters) | **Rejected** |
| **Do nothing (manual authoring)** | Zero | Highest | Highest (must recall syntax and write from scratch) | Full | **Rejected** |

## Workflow comparison

| Workflow mechanism | Strengths | Weaknesses | Fit |
| --- | --- | --- | --- |
| **Pure deterministic script** | Strict validation, zero-diff idempotency, fast unit tests | No session extraction or `$bmode` trigger | Insufficient alone |
| **Dedicated LLM-only skill** | Minimal Python code | Format drift, broken triggers, risk of overwriting manual edits | Unsafe |
| **Hybrid (`bmode` gate + thin explicit skill + deterministic CLI scaffolder)** | LLM extracts JSON only; stdlib CLI owns validation, rendering, `content-sha256`, `--dry-run` diffs, and atomic writes | ~350 LOC stdlib Python + schema + reference guide | **Chosen** |

## Decision

1. **Path invariant:** Captured repo assets live strictly under `<worktree-root>/.byte-stack/{playbooks,workflows}/<key>`.
2. **No silent or hook-driven writes:** No lifecycle hook writes `.byte-stack/`. Capturing requires caller opt-in, and `--dry-run` creates zero files or directories.
3. **Self-contained core:** `capture_playbook.py`, `capture-payload.schema.json`, and `capture-playbook.md` live inside `skills/bmode/` so selective `bmode` installs work independently. `skills/capture-playbook/` is a thin explicit entrypoint calling the same CLI.
4. **Stdlib boundary validation:** Extraction payloads conform to `capture-payload.schema.json` (Draft 2020-12) and are validated strictly with Python 3.9+ stdlib (`validate_payload()`).
5. **Single owner for keys & frontmatter:** `assets.py` owns `validate_key()` and `parse_frontmatter()`; `capture_playbook.py` imports them directly.
6. **Backward-compatible loader:** `assets.py` reads frontmatter `use-when:` first and falls back to `Use when: ` in the body, keeping all bundled and hand-authored playbooks working unchanged. Generated playbooks emit `use-when:` in frontmatter only.
7. **Manual-edit protection & idempotency:** Generated files record `managed-by: byte-stack/capture` and `content-sha256`. Repeat identical runs exit `0` (`unchanged`, zero diff, mtime preserved). Clean managed updates require `--update`. Manually edited or hand-authored files exit `3` (`conflict`) with unified diff and are untouched unless `--force` is explicitly supplied.

## Boundary connascence

| # | Crossing elements | Type | Locality | Degree | Verdict | Guard / Fix |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Agent extraction -> `capture_playbook.py` JSON | Name + Type | Cross-process | 2 | OK | Strict `capture-payload.schema.json` (`additionalProperties: false`) + stdlib validator |
| 2 | `capture_playbook.py` <-> `assets.py` | Algorithm + Meaning | Cross-script | 2 | Fixed | `assets.py` owns `validate_key()`, `checked()`, `parse_frontmatter()` |
| 3 | Stored `.byte-stack/*.md` <-> future `capture_playbook.py` | Algorithm + Meaning | Across releases | N repos | Watch | `schema-version: 1` + pinned golden `content-sha256` test |
| 4 | Generated file <-> `assets.py` (`use-when:` vs `Use when:`) | Meaning + Value | Across modules | 2 | Fixed | Emit `use-when:` in frontmatter only; `assets.py` rejects conflicting dual triggers |
| 5 | `bmode/SKILL.md` & `capture-playbook/SKILL.md` -> CLI | Name | Cross-skill | 2 | OK | Integration tests verify exact documented CLI contract |

## Consequences

- **Positive:** Repeatable repo choreography is captured immediately after verified runs with minimal base-context overhead, strict schema guarantees, and zero risk to hand-edited playbooks.
- **Negative / accepted costs:** Post-task triggering relies on model adherence to the 4-line `## Capture` gate in `bmode/SKILL.md`; adding `capture-playbook` consumes ~104 chars in the global skill list.
- **Trade-offs:** Flat scalar YAML frontmatter avoids a PyYAML dependency and is extensible under `schema-version`.

## Fitness functions

| ID | Invariant | Check | Runs in |
| --- | --- | --- | --- |
| `FF-CAP-1` | Schema validation, `--dry-run`, zero-diff idempotency, manual-edit protection, symlink safety, `$bmode` discovery | `python3 tests/test_byte_stack_capture.py` | Local + CI |
| `FF-CAP-2` | Backward compatibility of bundled/local playbooks & frontmatter parser | `python3 tests/test_byte_stack_assets.py` | Local + CI |
| `FF-CAP-3` | Zero Antigravity/Codex hooks added, valid manifests, no disallowed terms | `python3 tests/test_byte_stack_distribution.py && python3 tests/test_antigravity_plugin_install.py` | Local + CI |
| `FF-CAP-4` | `bmode/SKILL.md` <= 70 lines; `capture-playbook` description <= 140 chars | Assertions in `tests/test_byte_stack_capture.py` | Local + CI |

## Revisit when

- Claude Code, Antigravity, and Codex expose a common post-task hook and transcript API suitable for cross-host passive mining.
- Repositories need multi-file captured assets (such as paired `playbooks/` and `scripts/`) scaffolded atomically.
