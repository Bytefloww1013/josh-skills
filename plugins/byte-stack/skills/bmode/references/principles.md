# Principles in bphs-connect

Use this reference when you apply a principle under bmode. Read only the entry for the principle you are applying.

Each principle is a skill shipped next to bmode, written for any repo. Load it first, as `SKILL.md` (Principles) says. Its entry here says when it applies in bphs-connect, what it asks here, and where a repo rule narrows it. Where an entry and the leaf disagree, the entry wins, and the repo rules win over both.

## Core

### Laziness Protocol (`byte-stack:principle-laziness-protocol`)

- **When:** refactoring, sizing a diff, or tempted to add a wrapper, a one-caller adapter or a flag threaded through several modules.
- **Do:** make the smallest change that solves the problem, with each decision in one place.
- **Repo limits:** measure smallest inside the module rules and after the companions the repo requires in the same PR: stale docs, the generated registries, `bun.lock` and the `tables:refs` baseline.

### Foundational Thinking (`byte-stack:principle-foundational-thinking`)

- **When:** before writing logic in a module: its tables in `server/schema.ts`, its shared types, the order of a plan's phases, and what two accounts or jobs saving the same row share.
- **Do:** get the data shape right first, put scaffold phases before the features that use them, and decide what a second concurrent save does.
- **Repo limits:** commits still follow phases (`docs/directives/plans.md`). A shared type lives in the module's own `shared/` unless every module needs it.

### Redesign from First Principles (`byte-stack:principle-redesign-from-first-principles`)

- **When:** a new requirement lands on an existing module, table or lookup.
- **Do:** design it as if the requirement had been there from the start. Carry it through the code, docs, README `sources` and tests, then deliver it phase by phase. Decide the redesign in the plan, before the go-ahead.
- **Repo limits:** history is extended, never rewritten. An applied migration stays, and a conflict with an ADR is said out loud (`docs/agents/domain.md`).

### Attack the Premise (`byte-stack:principle-attack-the-premise`)

- **When:** two or more fixes that share one premise have failed the same gate, such as a Phase 1 loop, a regression test, a CI check or a hillclimb harness.
- **Do:** write the premise down and test it before you write another fix that assumes it.
- **Repo limits:** the gate stays as it is. Never accept a snapshot, rewrite a baseline, relax a stop rule or turn off a lint rule to get past it.

### Subtract Before You Add (`byte-stack:principle-subtract-before-you-add`)

- **When:** sequencing a feature, refactor or module move onto code that carries dead weight.
- **Do:** remove dead code, exports no module imports and stale doc lines first, then build on the simpler base.
- **Repo limits:** this covers code and docs only. Never subtract a table, a stored record, an audit entry or an applied migration this way (`PRODUCT.md`; "Remove a module" in `docs/references/modules.md`). The access declaration and the shared schemas are required, not speculative.

### Minimize Reader Load (`byte-stack:principle-minimize-reader-load`)

- **When:** reviewing or reshaping code that is hard to trace, or judging whether a refactor earned its keep.
- **Do:** count the layers between a question and its answer and the state a reader must hold, and cut whichever costs more.
- **Repo limits:** a module's `index.ts` files, hooks, slots and the generated registries are the repo's boundaries, not pass-through layers. A small named helper beside its only caller stays (`.oxlintrc.json`).

### Outcome-Oriented Execution (`byte-stack:principle-outcome-oriented-execution`)

- **When:** a planned rewrite or migration worked in phases, such as moving code between modules or replacing a module's storage.
- **Do:** aim every phase at the target shape and leave no compatibility shim behind.
- **Repo limits:** a slice may leave the typecheck or tests red only as Sequence Work into Verifiable Units allows (below). URLs, route access and stored data hold at every step.

### Experience First (`byte-stack:principle-experience-first`)

- **When:** scoping a feature with the user, choosing between UI variants, or shaping an API another module will call.
- **Do:** choose the work `PRODUCT.md`'s Product Principles put first (fast, keyboard-operable entry and trustworthy answers) over what is easiest to build. Propose cutting any control that does not earn its place.
- **Repo limits:** here the polish is the restraint `DESIGN.md` asks for, not extra motion. The user decides scope, and the UI rules in `PRODUCT.md` and the current design tokens hold.

### Exhaust the Design Space (`byte-stack:principle-exhaust-the-design-space`)

- **When:** a UI interaction, or a hard-to-reverse design choice, with no precedent in the architecture map, the module docs, `docs/adr/` or a sibling module.
- **Do:** build 2 or 3 competing variants or designs and compare them before committing. For a UI, use the `prototype` skill's UI.md switcher. For types, signatures or a module's shape, use the `byte-stack:architect` helper: it builds two plans, and `arch-skills:architecture-decision-review` picks and records one ([helpers.md](helpers.md), arch-skills).
- **Repo limits:** variants are prototypes, so they may run before the plan's go-ahead ([triggers.md](triggers.md), "A feature plan"). They stay on the Prototype playbook's throwaway branch. A question an ADR settled is reopened only by saying so.

### Build the Lever (`byte-stack:principle-build-the-lever`)

- **When:** any edit, sweep, analysis or check beyond a couple of obvious edits.
- **Do:** build the smallest script, generator or check that does or proves the work, as `bun run new-module` and `docs/verify/*` do, so a reviewer can rerun it.
- **Repo limits:**
  - A session lever lives under `tmp/`. The reply or the PR's `## How it was checked` gives its command.
  - A lever committed under `scripts/` or `docs/verify/` answers `--help` (`bun run scripts:help-check`). It gets its row in `docs/references/commands.md` from its header comment through `bun run docs:gen`.
  - A lever never runs a `**Stop:**` step.

## Architecture

### Model the Domain (`byte-stack:principle-model-the-domain`)

- **When:** writing stateful logic, a new status or kind, or code that branches on a Form question type, a custody kind or a record's state across files.
- **Do:** encode it in one structure named in the glossary's words, such as a table keyed by kind, a status worked out from stored rows, or a discriminated union, instead of conditionals spread across the module.
- **Repo limits:** the structure lives inside the module folder. A new module goes through the user-invoked `add-module` skill. A new glossary term needs the user's yes, then the `byte-docs-glossary` skill's `add <term>`.

### Boundary Discipline (`byte-stack:principle-boundary-discipline`)

- **When:** wiring a route's body, a webhook, an importer, `server/config.ts`, a script's arguments, or a module's public API.
- **Do:** parse outside data once at that edge (the module's shared Zod schema through `json(schema)` in `server/http.ts`) and trust the parsed type inside. A public API exports what other modules need.
- **Repo limits:**
  - A new reference to another module's table changes the `tables:refs` baseline, so the diff shows it (`docs/references/modules.md`, Boundaries).
  - This principle covers the system edge. An import across modules follows the Architecture rule in [repo-rules.md](repo-rules.md), not this principle.
  - Trusting the type never drops an access or visibility check in a service, and service rules stay in their transaction.

### Type System Discipline (`byte-stack:principle-type-system-discipline`)

- **When:** designing a type, a signature, a shared schema or a table entry.
- **Do:**
  - Derive types from their owner (`z.infer` from the Zod schema, `$inferSelect` from the Drizzle table, a mapped type over a union key) so `bun run typecheck` names every variant left unhandled.
  - Brand an id where two ids of different kinds meet in one signature.
  - Give a raw `sql` fragment its result type, as `sql<number>` in `modules/maintenance/server/summary.ts` does.
  - Read the `byte-stack:typescript-best-practices` helper ([../../typescript-best-practices/SKILL.md](../../typescript-best-practices/SKILL.md)) with this leaf.
- **Repo limits:** under `erasableSyntaxOnly`, a closed set is a string-literal union, never an `enum`. The helper's structured-telemetry row does not apply here: the server has no logger, and `console` is its log ([writing.md](writing.md), Comments and lint).

### Make Operations Idempotent (`byte-stack:principle-make-operations-idempotent`)

- **When:** writing a module `startup`, a job, a webhook, a migration that moves rows, or a `docs/verify` or `scripts/` command.
- **Do:** make it reach the same end state when run again after a restart, a retry or a crash. Read what is there and apply only the difference.
- **Repo limits:** a migration gets there by being all-or-nothing in its transaction (New migration playbook). The seed refuses a populated database on purpose. Safe to repeat never means free to run (`SKILL.md`, Autonomy).

### Migrate Callers Then Delete Legacy APIs (`byte-stack:principle-migrate-callers-then-delete-legacy-apis`)

- **When:** a module's public API, a hook, a slot, a manifest field or a kernel helper changes shape while callers still use the old one.
- **Do:** move every caller and delete the old shape in the same PR, with no alias, and update the tests to the new contract. Put the change in the plan before the go-ahead, so the user approves it there.
- **Repo limits:**
  - `docs/directives/versioning.md` ships the app as one image, so these shapes are internal. The contracts that directive names (environment variables, the Zoho webhook, data-changing migrations) follow the directive.
  - Under `--auto`, a public API change and deleting code the run did not make are `one-way-door` options, which the Decision subagent never picks.

### Separate Before Serializing Shared State (`byte-stack:principle-separate-before-serializing-shared-state`)

- **When:** two or more subagents, worktrees, claim runs or scratch servers might write the same file, branch, port or folder.
- **Do:** give each its own owned target first: its own files, worktree, `PORT` and `ROOT`. Each routes smoke gets its own `PORT` and `ROOT` too.
- **Repo limits:**
  - Stop a server on 3391 only when you started it or no other run owns it (AGENTS.md gotcha).
  - Never merge a generated file by hand (the module registries, `bun.lock`, the migration journal, the whole-repo baselines). Its command writes it again, as the Orchestrate playbook's step 4 says.

## Verification

### Prove It Works (`byte-stack:principle-prove-it-works`)

- **When:** before you call a slice, phase or task done, or rely on a subagent's report or a handoff's claim.
- **Do:** run the real thing on the seed or the scratch server (the test by name, the page through `browser.mjs`, the API through the test kit) and read what it printed. The scripted proof is the branch's git-ignored `verify-done.sh`, with its PASS lines under `## How it was checked`.
- **Repo limits:** when output looks wrong, suspect the condensing first and use `rtk proxy` as `SKILL.md`'s "Command output" rule allows. CodeGraph's results for locating code still stand.

### Fix Root Causes (`byte-stack:principle-fix-root-causes`)

- **When:** debugging a reported bug, a failing check or a live symptom.
- **Do:** trace the symptom back to the first place the code went wrong and fix it there. A guard, retry, catch or clamp is the fix only when the state it handles is legitimate.
- **Repo limits:** fix the instances the branch's issue covers and list the rest for the user. Instrument on the loop, the seed or the scratch server, since production instrumentation needs the user's permission.

### Sequence Work into Verifiable Units (`byte-stack:principle-sequence-verifiable-units`)

- **When:** a plan's phases and slices, a sweep across modules, or a run of similar edits.
- **Do:** check each slice (`bun run typecheck` and its touched tests) and each phase (`docs/verify/quick-check.sh`). Never start the next slice on red, except after a slice the plan's rules block names as allowed to stay red (Outcome-Oriented Execution). A phase never ends red.
- **Repo limits:** commit per phase, not per unit (`docs/directives/plans.md`), with a move and its reshape in one commit. The squash merge keeps one commit, so the PR body shows the red-then-green.

### Test Behavior, Not Implementation (`byte-stack:principle-test-behavior-not-implementation`)

- **When:** writing, changing or keeping a Vitest test, a regression test, or a pin for a refactor.
- **Do:** drive the code through what its users touch (the API through the test kit's `t.call`, a page on the scratch server) and assert what they can observe, with the expected value taken from the requirement. Read another module's rows back through its API.
- **Repo limits:** a pinned invariant, such as `server/access/route-declarations.txt` or an `explain query plan` check, counts as behavior.

### Explain the Number (`byte-stack:principle-explain-the-number`)

- **When:** before you measure, and before you trust, report or act on a timing (Perf issue, Hillclimb) or a skill change's effect (Eval).
- **Do:** write down the result that would change the decision, name what limits the number, and rule out errors, skipped or cached work, noise and an untuned side.
- **Repo limits:** volume comes from seed or harness-inserted rows, never live data or a backup. The report names the row count, the Node version and where the database lived.

## Delegation

### Guard the Context Window (`byte-stack:principle-guard-the-context-window`)

- **When:** a bulk read is coming, such as a long log, a HAR or trace, a transcript, a wide diff or a fan-out plan.
- **Do:** for code, call `codegraph_explore` first. Hand other bulk to a subagent and keep only its reduced finding in the main thread.
- **Repo limits:** the handoff guard ignores subagents, so cap each one's files and turns in its brief (the scout brief's `READ_CAP`). Its model is the policy's scout ([subagents.md](subagents.md)). On HANDOFF REQUIRED, the handoff comes first.

### Never Block on the Human (`byte-stack:principle-never-block-on-the-human`)

- **When:** about to ask "should I do X?" about reversible work on the issue's branch that no gate covers (after the go-ahead, when the work has a plan), such as a choice inside the plan, the order of slices, a fix for a failing check, or a line for the issue notes.
- **Do:** decide, do it, and report why (`SKILL.md`, Autonomy, "Decide and report").
- **Repo limits:** it covers nothing else. Every gate in Autonomy, the plan's question rounds, and the gates of user-invoked and vendored skills stay with the user.

## Meta

### Encode Lessons in Structure (`byte-stack:principle-encode-lessons-in-structure`)

- **When:** the same correction or instruction comes up a second time, in a session, a retro or an issue notes block.
- **Do:**
  - Encode it as a check the repo already runs, such as an `.oxlintrc.json` rule, a script listed in `docs/verify/gate-checks.txt`, or an `[enforced: <script>]` directive rule.
  - A lesson that needs judgment becomes the target behavior stated plainly, as an AGENTS.md gotcha in its "X -> Y" form, naming the failure it prevents. Use these sparingly.
  - When one class of mistake has come up twice, offer the `byte-stack:correct` helper. It removes the class at the highest level that works: architecture, then types, then a lint, then a test.
  - When reviews find a copied helper a second time, also offer `arch-skills:repo-navigability-audit` ([helpers.md](helpers.md), arch-skills).
- **Repo limits:** propose a new directive rule to the user rather than adding one. Ship a change to `scripts/docs*` or a directive in a PR of its own.
