---
name: bmode
description: Work in the bphs-connect repo, apply the principle skills beside this one as judgment under those rules, and follow one playbook per kind of task. Use for /bmode in bphs-connect.
disable-model-invocation: true
---

# bmode for bphs-connect

This skill routes work in `Bytefloww1013/bphs-connect`. Every path in this skill is relative to this skill's folder unless it names a repo file.

**Rule order.** The repo's rules and gates come first. Where a principle or a helper disagrees with a directive in `docs/directives/`, an AGENTS.md gotcha, a module README, a step in a skill written in this repo or in `Bytefloww1013/josh-skills`, or a user or operator gate, follow the repo rule or the gate.

## Load only what the task needs

Read this file in full. Open each other file only when its trigger fires, and read only the section you need.

| Open | When |
| --- | --- |
| `playbooks/<name>.md` | You matched the task to a playbook (Playbooks, below). Read it in full. |
| [references/triggers.md](references/triggers.md) | A conditional trigger in Non-negotiables fires. |
| [references/principles.md](references/principles.md) | You apply a principle. Read that principle's entry. |
| [references/repo-rules.md](references/repo-rules.md) | You add or move module code, change a skill written in this repo, or check a vendored skill's output. |
| [references/helpers.md](references/helpers.md) | A step names a byte-stack helper or an `arch-skills:` skill, or says to offer one. |
| [references/autonomy.md](references/autonomy.md) | You need to know who merges, how an `--auto` gate is decided, or what a hook enforces. |
| [references/subagents.md](references/subagents.md) | Before you spawn any subagent. |
| [references/writing.md](references/writing.md) | Before you write a doc, a skill, AGENTS.md, CLAUDE.md, a PR body or a commit, or change lint or format config. |
| [references/triage.md](references/triage.md) | The Babysit playbook meets a comment on a PR. |
| [references/t3-model-routing.md](references/t3-model-routing.md), [references/dispatch-loop.md](references/dispatch-loop.md) | Under T3, or when you route scouts, reviewers or implementors ([references/subagents.md](references/subagents.md) says when). |

## Non-negotiables

**Always on:**

- **New branch.** Name it by the branch rule in `docs/directives/git-and-prs.md` before its first commit, in place of any name the session hands over (such as a cloud session's `claude/...` branch). `bun run names:check` fails any other name.
- **The target is code** (reading a file or symbol, finding code, before an edit, tracing a flow). Call CodeGraph's `codegraph_explore` before Read, rg, Glob, find or an Explore agent. Trust its results and do not re-check them with grep or rg. Read config, Markdown, JSON and SQL migrations directly, since CodeGraph does not index them, and read any detail its output did not cover. If the MCP tool is unavailable, run `codegraph explore "<query>"`. **Do not run** `codegraph init`: a SessionStart hook builds the index.
- **Command output.** It is condensed. Treat it as the complete result. Re-run a command as `rtk proxy <cmd>` only when its result is unusable: empty when output was expected, contradicting its exit code, or garbled.
- **Checks.** Run `bun run format` before committing. `bun run lint` must exit 0 with no warnings. `bunx vitest run <path>` runs one test file. Run `docs/verify/quick-check.sh` after each phase. Done means the branch's `docs/verify/verify-done.sh` exits 0. Git ignores that file, and each branch writes its own from `docs/verify/verify-done.template.sh`. `docs/references/commands.md` lists every script.

**When the trigger fires:**

- **A feature plan.** Read [references/triggers.md](references/triggers.md), "A feature plan", before you write or work a plan. Implement nothing until the user gives the go-ahead.
- **A doc.** Read [references/triggers.md](references/triggers.md), "A doc".
- **A skill, AGENTS.md or CLAUDE.md.** Use the `writing-for-agents` skill, and its `SKILL-MECHANICS.md` for a skill. Run the Authoring playbook.
- **Modules** (you change `app.modules.ts`, a manifest or a `module.ts`, add a module, or move code between files or modules). Read [references/triggers.md](references/triggers.md), "Modules".
- **A new migration** (a branch changes a `schema.ts` or adds a file under `server/db/migrations/`). Run the New migration playbook.
- **Review agents** (a change crosses module or kernel boundaries, adds a migration, or touches API routes, access code or nav entries). Read [references/triggers.md](references/triggers.md), "Review agents", and call each agent whose trigger the change meets.
- **Production or a backup.** Follow `docs/directives/production-safety.md`, under the gates in Autonomy. A rehearsal on Staging runs the Upgrade staging playbook. An upgrade of production runs the Upgrade production playbook.
- **HANDOFF REQUIRED** from the handoff-guard hook. Run the Pause safely playbook with the skill the notice names (`byte-handoff`, the repo's copy). Tell the user about anything odd in the guard.
- **PR status** ("babysit this", "get it green", "check on PR X"). Run the Babysit playbook. Opening a PR does not start it. A request to merge, land or ship runs the Shipping playbook.
- **A GitHub issue.** Read [references/triggers.md](references/triggers.md), "A GitHub issue".
- **Domain words.** Use `docs/references/project-glossary.md`, never a `GLOSSARY.md`, even when a skill names one. Past decisions are the ADRs in `docs/adr/`.
- **A user-invoked skill** (`disable-model-invocation: true`). Only the human can start it. When the task needs one, ask the user to run `/<name>`. bmode's own helpers are the exception ([references/helpers.md](references/helpers.md)).

## Principles

The principle skills ship next to this skill and are model-invocable. Each one is a judgment guide written for any repo, applied under the repo's rules.

**To apply a principle:**

1. Load it this session. Invoke its skill ID below with the Skill tool. If the Skill tool cannot load it (for example, a delegate on a non-Claude model, or a session without byte-stack installed), Read `../principle-<name>/SKILL.md` in full instead.
2. Read its entry in [references/principles.md](references/principles.md). The entry says what the principle asks in bphs-connect and where a repo rule narrows it.
3. In the reply, name each principle that shaped a decision and the specific choice it changed. Cite only principles you loaded this session.

| Group | Principle | Skill ID | Apply when |
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
| Architecture | Boundary Discipline | `byte-stack:principle-boundary-discipline` | Wiring a route body, webhook, importer, `server/config.ts`, script args or a public API. |
| Architecture | Type System Discipline | `byte-stack:principle-type-system-discipline` | Designing a type, signature, shared schema or table entry. |
| Architecture | Make Operations Idempotent | `byte-stack:principle-make-operations-idempotent` | Writing a `startup`, job, webhook, row-moving migration, or `docs/verify` or `scripts/` command. |
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

## Autonomy

**Decide and report.** For reversible work on the issue's branch that no gate below covers (after the go-ahead, when the work has a plan), such as a choice inside the plan, the order of slices, a fix for a failing check or a line for the issue notes: make the call, do it, and give the reason in the reply (Never Block on the Human). Anything that cannot be undone, or that posts outside the repo (a comment, an issue, a label), still needs the user's word, unless it is a step of a skill the user started. This never waives a gate below, a plan's question rounds, or a gate in a skill, such as `tdd`'s seam confirmation or a `/byte-gh-issue-claim` approval.

**Needs the user's word:**

- Never push to `main`. Merge a PR only when the user says to (`docs/directives/git-and-prs.md`). A Decision subagent never stands in for that word, even under `--auto`.
- Open a PR only with the user's explicit say-so, given case by case (`docs/directives/git-and-prs.md`). Running `/byte-gh-issue-claim <N> --auto` is that say-so for the issue's own PR. Without `--auto`, the claim skill asks at Step 9 and, on a no, ends with the branch pushed and no PR.
- Implement a plan only after the user's go-ahead, unless the user gave explicit permission.

**Pushing a branch** other than `main` needs no say-so.

**Needs the operator's go-ahead** (`docs/directives/production-safety.md`):

- A how-to step that can't be undone (it starts the app, restores a database, deletes the databases a restore set aside, or runs `admin.ts`) carries a `**Stop:**` line. Never run it without the operator's go-ahead, given in that session for that step. A step that is safe to repeat still needs the go-ahead for each run.
- Never use a real backup or a copy of the live database for development work or tests. Use the seed or the scratch server (`docs/verify/scratch-server.sh`). Staging is the exception, for rehearsing upgrades only. Read Staging's database or its pulled backups only through the staging script, and never copy them into the repo, `tmp/` or a test.

Who merges, how `--auto` decides, and which hooks are wired: [references/autonomy.md](references/autonomy.md).

## Helpers and subagents

- **Helpers.** Before you run or offer a byte-stack helper or an `arch-skills:` skill, read [references/helpers.md](references/helpers.md).
  - Load these with the Skill tool when their condition comes up, even if no step names them: `byte-stack:how` (you need a working model of code before you change it), `byte-stack:blast-radius` (a change reaches a public API, hook, slot, migration or the kernel), `byte-stack:architect` (a design choice with no precedent), `byte-stack:typescript-best-practices` (you write or review `.ts` or `.tsx`), `byte-stack:technical-writing` (a doc, ADR, PR body or commit), `byte-stack:docs-add` and `byte-stack:docs-review` (a new doc, or code a doc describes), `byte-stack:gen-issue` (filing an issue).
  - The table in helpers.md gives each helper's full trigger and whether it runs by Skill tool or by Read.
- **Subagents.** Before you spawn a subagent, read [references/subagents.md](references/subagents.md). It sets each role's model, brief and report check.

## Writing the reply

Each playbook's **Reply:** line names what to report. Add:

- **Principles.** Each principle that shaped a decision, with the choice it changed, cited only from principles loaded this session. When you cite Build the Lever, give the lever's command.
- **Calls made without asking.** Each one, with its reason, so the user can correct it (Never Block on the Human).
- **Helpers.** Each helper you ran and what came of it, such as the plan architect picked or the fact blast-radius proved. Report each arch-skills run beside them with its verdict: the decision and its mode, the report's counts, pr-erosion-check's verdict, or that the plugin was unavailable. Under T3, give each routed step's model and level, and any fallback to Opus.

Write the reply through the `byte-stack:unslop` helper (`../unslop/SKILL.md`). For docs, agent-facing text, PR bodies, commits and lint, follow [references/writing.md](references/writing.md).

## Playbooks

Match the task to one playbook below. Open it and follow its steps in order. Its **Skills:** line lists the skills to load and when. Each playbook lists what is not established in bphs-connect for its kind of task.

- If no playbook fits, follow AGENTS.md and the directives, and tell the user that no playbook covers the task.
- For a large or multi-part task with no playbook, run the `byte-stack:figure-it-out` helper to design one first.
- Every other playbook ends by running **Opening a PR**.

| Playbook | File | Use when |
| --- | --- | --- |
| Investigation | [playbooks/investigation.md](playbooks/investigation.md) | A read-only question. Deliver a cited answer from CodeGraph and the repo's maps. |
| Bug fix | [playbooks/bug-fix.md](playbooks/bug-fix.md) | A reported defect, on a `bug/...` branch, from a loop that goes red on the bug. |
| Perf issue | [playbooks/perf-issue.md](playbooks/perf-issue.md) | Measured slowness, with a before and an after from the same command. |
| Hillclimb | [playbooks/hillclimb.md](playbooks/hillclimb.md) | Sustained improvement of one metric against a target: one change, one measurement, keep or revert. |
| Runtime forensics | [playbooks/runtime-forensics.md](playbooks/runtime-forensics.md) | Diagnose a live symptom from server, request and browser output. |
| Trace forensics | [playbooks/trace-forensics.md](playbooks/trace-forensics.md) | Diagnose a captured artifact handed over after the fact. |
| Feature | [playbooks/feature.md](playbooks/feature.md) | New or changed behavior, on a `feature/...` branch. |
| Refactoring | [playbooks/refactoring.md](playbooks/refactoring.md) | A behavior-preserving change, on a `refactor/...` branch. |
| New migration | [playbooks/new-migration.md](playbooks/new-migration.md) | A schema change and the migration `bun run db:generate` writes for it. |
| Prototype | [playbooks/prototype.md](playbooks/prototype.md) | A throwaway sketch to settle a design question. |
| Visual parity | [playbooks/visual-parity.md](playbooks/visual-parity.md) | UI equivalence judged by eye from screenshots of the seeded scratch server. |
| Authoring or modifying a skill | [playbooks/authoring-a-skill.md](playbooks/authoring-a-skill.md) | Writing or changing a skill, with its doc at `docs/skills/<name>.md` in the same PR. |
| Eval | [playbooks/eval.md](playbooks/eval.md) | Testing how a skill or prompt change affects agent behavior. |
| Babysit | [playbooks/babysit.md](playbooks/babysit.md) | Drive one PR to green, then stop. It never merges. |
| Shipping | [playbooks/shipping.md](playbooks/shipping.md) | Land a PR, only on the user's word. |
| Upgrade staging | [playbooks/upgrade-staging.md](playbooks/upgrade-staging.md) | Rehearse an upgrade, or a branch's migration, on Staging. |
| Upgrade production | [playbooks/upgrade-production.md](playbooks/upgrade-production.md) | Ship a tagged release to the VPS. |
| Autonomous run | [playbooks/autonomous-run.md](playbooks/autonomous-run.md) | Drive one task to an exit condition of checks that exit 0, such as `/byte-gh-issue-claim <N> --auto`. |
| Orchestrate | [playbooks/orchestrate.md](playbooks/orchestrate.md) | A standing program of many issues under one coordinator, one PR per ticket built by delegates. |
| Autopilot-full | [playbooks/autopilot-full.md](playbooks/autopilot-full.md) | A queue of issues, each run to green and reviewed on its own PR from `main`. |
| Autopilot-stack | [playbooks/autopilot-stack.md](playbooks/autopilot-stack.md) | Autopilot-full that stops at green and reviewed and hands the PRs to the user. |
| Session pickup | [playbooks/session-pickup.md](playbooks/session-pickup.md) | Resume prior work from the handoff, the plan, the branch and the issue. |
| Pause safely | [playbooks/pause-safely.md](playbooks/pause-safely.md) | A clean stop with a `byte-handoff` handoff, on request or on HANDOFF REQUIRED. |
| Multi-phase or multi-PR plan | [playbooks/multi-phase-plan.md](playbooks/multi-phase-plan.md) | A feature plan, a spec with tickets, or a `wayfinder` map, written before any build. |
| Worktree and simulator cleanup | [playbooks/worktree-cleanup.md](playbooks/worktree-cleanup.md) | Remove merged, clean worktrees and their branches. |
| Opening a PR | [playbooks/opening-a-pr.md](playbooks/opening-a-pr.md) | The end of every other playbook: branch, commits, docs, body, gates, erosion check, push; open only on the user's say-so. |
