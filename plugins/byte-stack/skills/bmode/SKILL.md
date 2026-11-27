---
name: bmode
description: Route a repository task to a bundled or repo-local playbook and apply the relevant engineering principles.
disable-model-invocation: true
argument-hint: "[playbook key] <task>"
---

# Bmode

Read the target repository's instructions. Respect the user's scope and approval gates. Use the installed skill directory shown by your host as the base for the commands below. Run commands from the task checkout, including when the skill is installed elsewhere.

## Choose and run a playbook

1. If the user supplied a key, resolve that key directly (append `.md` if omitted). Otherwise run `python3 "<bmode directory>/scripts/assets.py" list-playbooks` and match the task against the returned descriptions. When two distinct entries fit equally, give the user the choice. If none fits, say so. For a large uncovered task, use figure-it-out when available; otherwise follow the repository’s instructions.
2. Run `python3 "<bmode directory>/scripts/assets.py" resolve playbooks "<key>"`. Read the file at the path after the tab, then follow its steps. Report the selected key and origin with the result. An investigation is read-only.
3. Resolve every named workflow, reference or optional script with the same command, substituting `workflows`, `references` or `scripts`. Read Markdown on demand. For scripts, inspect the resolved file and run it only as part of the authorized step. If the resolver command fails or its execution is denied, report the diagnostic and stop that lookup. Never bypass it by opening a bundled path directly. For an unknown explicit key list available playbooks or the files of that kind. Optional assets may be absent.
4. Follow any playbook request for a helper using the host's skill mechanism or by reading the installed helper's SKILL.md. If an optional helper is unavailable, carry out its portable step directly and disclose the limitation. Refer to the target checkout's rules for checks, issue tracking, branches, external actions and production work. Never open a PR or merge without the user's authorization.

## Principles

Apply the relevant principle skills when their triggers match. Read each available principle's SKILL.md before citing it. The principle name and trigger remain usable in a selective bmode install.

| Area | Principle | Skill | Trigger |
| --- | --- | --- | --- |
| Core | Laziness Protocol | `byte-stack:principle-laziness-protocol` | Refactoring, sizing a diff, or tempted to add a wrapper, adapter or threaded flag. |
| Core | Foundational Thinking | `byte-stack:principle-foundational-thinking` | Before writing a module's logic: its tables, shared types, phase order, concurrent saves. |
| Core | Redesign from First Principles | `byte-stack:principle-redesign-from-first-principles` | A new requirement lands on an existing module, table or lookup. |
| Core | Attack the Premise | `byte-stack:principle-attack-the-premise` | Two or more fixes sharing one premise failed the same gate. |
| Core | Subtract Before You Add | `byte-stack:principle-subtract-before-you-add` | Building a feature, refactor or module move on code with dead weight. |
| Core | Minimize Reader Load | `byte-stack:principle-minimize-reader-load` | Code is hard to trace, or you judge whether a refactor earned its keep. |
| Core | Outcome-Oriented Execution | `byte-stack:principle-outcome-oriented-execution` | A planned rewrite or migration worked in phases. |
| Core | Experience First | `byte-stack:principle-experience-first` | Scoping a feature, choosing UI variants, or shaping an API another module calls. |
| Core | Exhaust the Design Space | `byte-stack:principle-exhaust-the-design-space` | A UI interaction or hard-to-reverse design choice with no precedent. |
| Core | Build the Lever | `byte-stack:principle-build-the-lever` | Any edit, sweep, analysis or check beyond a couple of obvious edits. |
| Architecture | Model the Domain | `byte-stack:principle-model-the-domain` | Stateful logic, a new status or kind, or branching on a kind or state across files. |
| Architecture | Boundary Discipline | `byte-stack:principle-boundary-discipline` | Wiring a route body, webhook, importer, configuration, script args or a public API. |
| Architecture | Type System Discipline | `byte-stack:principle-type-system-discipline` | Designing a type, signature, shared schema or table entry. |
| Architecture | Make Operations Idempotent | `byte-stack:principle-make-operations-idempotent` | Writing a job, webhook, migration, or repeatable command. |
| Architecture | Migrate Callers Then Delete Legacy APIs | `byte-stack:principle-migrate-callers-then-delete-legacy-apis` | A public API, hook, slot, manifest field or kernel helper changes shape while callers use the old one. |
| Architecture | Separate Before Serializing Shared State | `byte-stack:principle-separate-before-serializing-shared-state` | Two or more subagents, worktrees, claim runs or scratch servers might write the same target. |
| Verification | Prove It Works | `byte-stack:principle-prove-it-works` | Before calling work done, or relying on a subagent's report or a handoff's claim. |
| Verification | Fix Root Causes | `byte-stack:principle-fix-root-causes` | Debugging a reported bug, a failing check or a live symptom. |
| Verification | Sequence Work into Verifiable Units | `byte-stack:principle-sequence-verifiable-units` | A plan's phases and slices, a cross-module sweep, or a run of similar edits. |
| Verification | Test Behavior, Not Implementation | `byte-stack:principle-test-behavior-not-implementation` | Writing, changing or keeping a test, a regression test or a refactor pin. |
| Verification | Explain the Number | `byte-stack:principle-explain-the-number` | Before measuring, or trusting a timing or a skill change's effect. |
| Delegation | Guard the Context Window | `byte-stack:principle-guard-the-context-window` | A bulk read is coming: long log, HAR, trace, transcript, wide diff, fan-out plan. |
| Delegation | Never Block on the Human | `byte-stack:principle-never-block-on-the-human` | About to ask "should I do X?" about reversible work that no gate covers. |
| Meta | Encode Lessons in Structure | `byte-stack:principle-encode-lessons-in-structure` | The same correction or instruction comes up a second time. |

## Helpers

For a subsystem or ownership question, use how. For effects on callers, use blast-radius. Use architect when the implementation hinges on an unresolved design choice. Use docs-add for a new procedure or reference and docs-review to check claims against code. Use figure-it-out to design an uncovered multi-part workflow. Use capture-playbook to save a proven repo workflow into `.byte-stack/`. Use extract-assets to scan a repository and propose `.byte-stack/` assets. Each helper may run directly from the host. Invoke optional companion skills only when installed and relevant. On hosts without a dedicated Skill tool, read the selected skill’s installed SKILL.md. Use the host’s read, search and delegation equivalents.

## Capture

After a verified task in a Git worktree runs repeatable repo-specific steps or checks absent from existing playbooks, append one line: `Reusable repo workflow detected (<key>): save to .byte-stack/<kind>/<key>? (y/N)`.
Never prompt on read-only Q&A (`investigation.md`), one-offs, unverified or interrupted runs, `byte-agent` delegates, headless runs, or when `.byte-stack/.no-capture-prompt` exists.
Only after the user opts in, resolve `references/capture-playbook.md` and run `scripts/capture_playbook.py` (`--dry-run` first).

## Delegation

Use an available delegate only when permitted. Give it the absolute target worktree, the installed bmode directory, its playbook key, scope, expected result and allowed actions. It must resolve assets in its assigned checkout. Inherit the host selection unless the user or applicable repo policy specifies a supported target. Report an unavailable explicitly requested target. For a structured scout, implementation or review brief, resolve `references/subagents.md` and follow it.

Prefer `rg` for search. Keep parallel writes in separate worktrees, run the repository's documented checks, and verify the result at the normal entry point. Include remaining uncertainties in the handoff.
