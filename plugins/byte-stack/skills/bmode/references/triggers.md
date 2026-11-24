# Conditional triggers

Use this reference when one of these triggers in `SKILL.md` (Non-negotiables) fires. Read the section for that trigger before you act on it. They are non-negotiable: the principles bend to them.

## A feature plan

1. Follow `docs/directives/plans.md`.
2. Question the user over several rounds.
3. Write `<feature_name>-plan.md` at the repo root. Build it from phases of slices, each slice with a checkbox.
4. Implement nothing until the user gives the go-ahead.
5. After the go-ahead, commit the code once per phase, after that phase's boxes are ticked.

A prototype is an experiment run before implementation begins, not implementation. It may run during the question rounds to settle a question (Prototype playbook). Its code stays on its throwaway branch, and the real build waits for the go-ahead.

The plan stays out of git: `.gitignore` ignores every root `*-plan.md`. The PR body carries what a reviewer needs from it.

## A doc

- Follow `docs/directives/writing-docs.md`. How to write it is in [writing.md](writing.md), Docs.
- Create a new doc with the `byte-stack:docs-add` skill. When a PR changes code a doc describes, run `byte-stack:docs-review` on it.
- Update every doc the change makes stale in the same PR, or excuse it in the PR body with a `docs-unaffected: <doc> - <reason>` line.
- Put a change to the docs system itself in a PR of its own.

## Modules

- After changing `app.modules.ts`, a manifest or a `module.ts`, run `bun run modules:gen`.
- Create a new module through the `add-module` skill (`bun run new-module <id> [--foundation]`).
- To move code between files or modules, follow "Change a module" in `docs/references/modules.md`: move first, then reshape.
- The GOTCHAS in AGENTS.md name the traps in each area.

## Review agents

Call each agent whose trigger the change meets:

| The change | Agent |
| --- | --- |
| Adds or changes an import, a manifest's `dependsOn`, a server hook or a web slot between `foundation/<id>/`, `modules/<id>/` and the kernel (`server/`, `web/src/`, `shared/`); moves code between them; or adds a feature's code to the kernel or to another module's folder | `module-boundary-reviewer` |
| Adds a migration | `migration-reviewer` |
| Changes an API route, the access code (`server/access/`, `shared/permissions.ts`, `web/src/nav/address.ts`), a route's `staticData`, or a nav entry's `to`, `workspace`, `section` or `visible` | `access-reviewer` |
| Changes only a nav entry's group, order, label or icon | none |

- Give each agent the diff: paste `git diff <base>...HEAD` into its brief, or save it to a file and name that file by its absolute path.
- `review-team` runs each agent whose trigger its change meets. Outside `review-team`, nothing in the repo calls them, so call them yourself.
- A branch about to be pushed for its PR, and a delegate's PR before a coordinator merges it, also gets `arch-skills:pr-erosion-check` ([helpers.md](helpers.md), arch-skills).
- Under T3, that branch then gets a Sol review ([t3-model-routing.md](t3-model-routing.md)).

## A GitHub issue

- Issues live on `Bytefloww1013/bphs-connect`. Work them with `gh` (`docs/agents/issue-tracker.md`).
- `/byte-gh-issue-claim <N>` works one issue end to end.
- The `byte-stack:gen-issue` skill files one, with exactly one `one-way-door` or `two-way-door` label.
- Never create a label. `docs/agents/triage-labels.md` maps triage roles to the repo's labels.
