# Repo rules

Use this reference when you need to know where bphs-connect keeps a rule: before you add or move module code, before you change a skill written in the repo, or when you hold a vendored skill's output to the repo's standards. The principles bend to these rules.

## Directives

- `docs/directives/` holds `git-and-prs.md`, `plans.md`, `production-safety.md`, `versioning.md` and `writing-docs.md`.
- Each rule under a directive's `## Rules` is either checked by a script (`[enforced: <script>]`) or tagged `[judgment]`.
- `bun run docs:check --rules` lists every `[judgment]` rule.

## Architecture

- The map is `docs/references/architecture.md`.
- How to add, change, depend on or remove a module is in `docs/references/modules.md`.
- Each module's rules are in its own `README.md`.
- A feature's tables, rules, API, pages, seed, tests and README go in its module folder.
- Import another module only through its public API (`server/index.ts`, `shared/index.ts`, `web/index.ts`), and name it in the manifest's `dependsOn`.
- To learn something from other modules, ask a server hook or draw a web slot. Never import them for it.

## Skills written in this repo

- `add-module` and `byte-docs-glossary` are not in `skills-lock.json`.
- `byte-handoff` is not in `skills-lock.json` either. It and `.claude/hooks/handoff-guard.py` are byte-identical copies of byte-stack's own, kept for cloud sessions, which don't install plugins. Change them in `Bytefloww1013/josh-skills`, then refresh the copies (`docs/skills/byte-handoff.md`).
- byte-stack ships `docs-add`, `docs-review` and `gen-issue`, so a cloud session has none of them.
- `docs-add` and `docs-review` are written for this repo. They run its `bun run docs:*` scripts, and `docs-review` launches its `byte-docs-review-*` agents.

## Vendored skills

- `skills-lock.json` lists the skills that come from other repos. Their docs in `docs/skills/` say "Written for any repo, not this one: it doesn't know this repo's directives, glossary words or doc rules."
- They include `writing-for-agents`, `diagnosing-bugs`, `tdd`, `prototype`, `research`, `code-review`, `codebase-design`, `pr`, `retro`, `implement`, `improve`, `to-spec`, `to-tickets` and `wayfinder`.
- They are tools the repo installed, not house practice. Hold what they produce to the directives and the glossary.
- Where a vendored skill and a principle differ on method, follow the principle.
- Neither lifts a gate the skill puts before the user, such as `tdd`'s seam confirmation.
