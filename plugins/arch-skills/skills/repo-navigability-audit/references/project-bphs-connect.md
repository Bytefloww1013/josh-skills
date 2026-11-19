# Project profile: bphs-connect

Read this first when the repo has `app.modules.ts` and `docs/verify/gate-checks.txt` (the BPHS-Connect app). It tells the skill which of its own checks the repo already runs, so the skill runs those and spends its effort on what they cannot see.

Written from the repo at release 6.1.5 (November 2026). Where this file and the repo's own docs disagree, the repo's docs win: read `AGENTS.md`, `docs/references/architecture.md` and `docs/references/modules.md` for the rules as they are today.

## Contents
- Stack and layout
- Script flags for this repo
- Checks the repo already runs (do not re-derive these)
- Decision records and rules
- Issues, branches and PR scope
- Other review tools in the repo
- Known baseline facts
- SQL

## Stack and layout

- TypeScript only for app code (`.ts`, `.tsx`). React SPA (`web/`), Hono API (`server/`), SQLite through Drizzle ORM. Bun runs scripts; the server runs `.ts` directly under Node.
- **Kernel:** `server/`, `web/src/`, `shared/`. **Foundation modules:** `foundation/<id>/`. **Feature modules:** `modules/<id>/`. Each module has `server/`, `shared/`, `web/` sides and a `README.md` with its own rules.
- **Public API of a module:** `server/index.ts`, `shared/index.ts`, `web/index.ts`. Another module imports only these, and only if its manifest's `dependsOn` names that module.
- **Cross-module learning without imports:** server hooks (`ServerHooks` in `server/modules.ts`) and web slots (`SlotProps` in `web/src/modules.ts`). ADR 0006 keeps every hook and slot declared in the kernel.
- **Generated registries:** `shared/modules.gen.ts`, `server/modules.gen.ts`, `web/src/modules.gen.ts`. They are the composition root; the kernel reaches feature modules only through them.
- **Path aliases:** `#kernel/*` = `server/*`, `#shared/*`, `#foundation/*`, `#modules/*` (package.json `imports`); `@/` = `web/src/`, `@shared/` = `shared/` (web only).

## Script flags for this repo

```
AREAS="--area kernel=server --area kernel=web/src --area kernel=shared --area 'foundation/*' --area 'modules/*'"
python3 scripts/coupling_metrics.py --root . --module kernel=server --module kernel=web/src --module kernel=shared \
  --module 'foundation/*' --module 'modules/*' --skip-tests --exclude 'scripts/*' --exclude 'docs/*' --json
python3 scripts/diff_scan.py /tmp/pr.diff --repo . $AREAS
git diff --name-only origin/main...HEAD | python3 scripts/scope_check.py - --branch "$(git branch --show-current)" --body tmp/pr-body.md $AREAS
git diff --name-only origin/main...HEAD | python3 scripts/adr_match.py --adr-dir docs/adr --rules-dir docs/directives -
```

The coupling script reads the aliases from `package.json` and the tsconfig files by itself and leaves the `*.gen.ts` registries out.

## Checks the repo already runs (do not re-derive these)

`docs/verify/gate-checks.txt` lists every CI check. The ones that overlap these skills:

| Check | What it enforces | What the skill does instead |
|---|---|---|
| `bun run lint` (rule `boundaries/imports`, rules a to h in `scripts/oxlint-boundaries.ts`, plus `lint:cycles`) | web never imports server; foundation never imports a feature module; outside code imports only a module's public `index.ts` (table files excepted, ADR 0012: a module's `server/schema.ts` may import another module's `server/schema.ts`, and kernel server code a foundation module's); shared never imports server or web; confidential modules never reach notifications or mentions; kernel reaches feature modules only through the registries; a module imports only modules in its `dependsOn`; a table file imports only `drizzle-orm`, the kernel's `columns.ts`/`schema.ts`, other table files and, type-only, its own `shared/` (rule h); no file-level import cycle | Run it (or read its CI result). A failure is a confirmed finding; quote the lint line. Never re-check these by hand. Spend the time on connascence the import rule cannot see: shared meaning, positions, values and timing. |
| `bun run tables:refs` | a module that starts to reference another module's table (Drizzle import or raw SQL), or an existing reference spreading to a new file, against `scripts/tables-refs.baseline.json` | Run it. A new pair is Value connascence across modules: judge whether a server hook or the owner's public API should carry the data instead. A baseline change in the diff (`--write`) needs a reason in the PR body. |
| `bun run migrations:check`, `bun run migrations:fks`, `docs/verify/schema-drift.sh` | migration journal order, applied migrations unchanged, foreign keys, schema drift | Run them. For the design of a schema change (expand and contract, who owns the table), use `contracts-evolution.md`; for SQLite rebuild rules, the repo's `migration-reviewer` agent. |
| `bun run modules:gen --check` | registries match the manifests | Run it; a stale registry is a fix, not an architecture finding. |
| `bun run docs:stale` | a PR edits each doc whose `sources` it changes, or excuses it with `docs-unaffected: <doc> - <reason>` | Run it. Do not report stale docs again. |
| `bun run names:check` | branch name `<descriptor>/<action>-issue<N>-<words>` and Conventional Commit title | Run it. The branch name gives the issue number for the scope check. |

`docs/verify/quick-check.sh` runs all the `quick` checks in one go.

## Decision records and rules

- ADRs are in `docs/adr/`. Format: front matter with `description`, `sources` (the files the decision governs) and `enforced-by`; a `# Title`; a `Status: accepted (issue #N).` line; the decision in the opening paragraphs; `## Considered Options`; the evidence; `## What would reopen it`. `adr_match.py` reads this format.
- Rules are in `docs/directives/`. Each rule ends in `[judgment]` (a reviewer checks it) or `[enforced: <script>]` (a script checks it). Review only the `[judgment]` rules that `adr_match.py --rules-dir docs/directives` prints for the changed files.
- When architecture-decision-review writes a decision record here, write it in the repo's ADR format, not the template in `decision-frameworks.md`. Map: Scope globs go in `sources`; fitness functions go in `enforced-by` (scripts) and in the text; "Revisit when" becomes `## What would reopen it`. Keep the status `proposed` until the owner accepts it.
- Feature plans follow `docs/directives/plans.md`; docs follow `docs/directives/writing-docs.md` (plain words, one idea per sentence).

## Issues, branches and PR scope

- One GitHub issue per PR is the norm; a few related issues sometimes share one. The branch name carries the issue: `feature/build-issue30-docs-context-system`.
- The PR body is drafted in `tmp/pr-body.md` (ignored by git). Pass it to `scope_check.py --body`.
- Scope is judged per area. A change in `modules/<a>` for an issue about `modules/<b>` needs a sentence in the issue or PR body that explains it. Kernel changes need the same.
- A change to the docs system itself (the `scripts/docs*` checks, the directives, the doc header) goes in its own PR (`git-and-prs.md`, judgment rule). Treat a mix as a scope finding.
- There is no size limit. CI scope goes by paths, never by size.

## Other review tools in the repo

The repo has its own skills and agents. Use them where they fit; do not duplicate their work.

| Tool | What it covers | How it fits |
|---|---|---|
| `code-review` skill | Standards (repo coding rules) and Spec (does the code do what the issue asked) | pr-erosion-check covers structure and agent shortcuts. Do not report spec gaps here; say "spec: see code-review". The scope check asks a narrower question: does the change go beyond the issue? |
| `review-team` skill | a fleet of reviewer agents, including an architecture reviewer | pr-erosion-check can serve as that architecture lens. |
| `module-boundary-reviewer` agent | reads the module docs and judges cross-module changes | For a High or Critical boundary finding, it is a good fresh-eyes verifier. |
| `migration-reviewer` agent | migrations and schema changes against SQLite and production-safety rules | Hand schema changes to it; report its result under the contract lens. |
| `codebase-design`, `improve-codebase-architecture` skills | deep-module vocabulary; finding deepening opportunities | architecture-decision-review can borrow their vocabulary (seam, deep module). |

## Known baseline facts

Scanned at the commit above with the flags in this file. Use them to tell new problems from old ones; re-run before relying on them.

- The kernel and five foundation modules (audit, employees, mentions, notifications, programs) form one module-level import cycle (rescanned at release 7.2.0; assignments left it when its table file stopped importing public APIs, #624). The boundary rule allows kernel to foundation imports, so this is by design today. The kernel's imports of mentions are type-only; `lint:cycles` keeps the file-level graph cycle-free. Report only **new cycle edges** (`new_cycle_edges` from `--compare`), never the old cycle.
- Leaving the generated registries out, the kernel imports no feature module. A new kernel import of a feature module fails lint (rule f) before it reaches review.

## SQL

The SQL here is generated by drizzle-kit from each module's `server/schema.ts`, plus some raw SQL inside `sql` templates. The skills do not parse SQL into the import graph: `tables:refs` already finds cross-module table use, with a baseline, and does it better than a regex would. Treat its output as the SQL lens. For a new table or column, ask who owns it (the module whose `schema.ts` defines it) and whether other modules read it through that owner.
