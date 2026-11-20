# Council review in bphs-connect

The repo's rules win over this profile and over the skill. They are in `AGENTS.md`, `docs/directives/`, the module READMEs and `docs/adr/`. Give each seat this file's absolute path and the section for the kind under review.

## Before the council

- Code: `docs/verify/quick-check.sh` passes, or `docs/verify/verify-done.sh` when the branch has one. The review agents whose trigger the change meets have run (`module-boundary-reviewer`, `migration-reviewer`, `access-reviewer`), and so has `arch-skills:pr-erosion-check` on a branch about to get its PR. The council comes after these and does not replace them. Put their results in the packet.
- UI: start `docs/verify/scratch-server.sh start`. Take screenshots with `node docs/verify/browser.mjs --as <priya|marcus|rosa> --width <px> --out <folder> <address>...` on the base and on the head, at 1440 and 390 px. Use all three accounts when the page shows something different by access level: priya is Super Admin, marcus has Edit, rosa has Read Only. A FAIL line (a console error or an error page) is a finding before the council starts. Stop the server afterwards.
- Plan: the plan follows `docs/directives/plans.md`. The plan file is untracked, so give the seats its absolute path in this checkout, with `isolation: shared`.

## What every seat checks, any kind

- The words match the project glossary (`docs/references/project-glossary.md`). A new word for an existing thing counts as a finding.
- Scope matches the issue or plan, nothing more. Note anything extra.
- The change fits how the repo is built (`docs/references/architecture.md`, `docs/references/modules.md`): kernel, foundation and feature modules; another module only through its public API and `dependsOn`; hooks and slots, not imports.
- Production safety (`docs/directives/production-safety.md`) for anything that touches data, migrations, backups or deploys.

## Code

- Correctness at the edges: empty, missing, a second account, a stale tab, a concurrent writer.
- Access: every API route's first handler is its access declaration. A page's address decides who can open it (`addressVerdict`), and a page with no nav entry declares `needs` or `forwards` in `staticData`. The server and the address verdict ask for the same level.
- Data: a migration runs in one transaction with foreign keys on (see the AGENTS.md gotcha). Tables live where drizzle-kit reads them.
- Types come from their owner (`z.infer`, `$inferSelect`). A closed set is a string-literal union, never an `enum`.
- Tests test behaviour, restore what they change, and cover the issue's cases. No weakened or skipped test.
- No copied helper: search with CodeGraph for an existing one.
- `bun run lint` exits 0 with no warnings. No `oxlint-disable` comments.
- A doc the change makes stale is updated in the same PR (`docs:stale`).
- CI time: a new CI job or a slower test needs a reason (the user weighs CI minutes).

## UI change

- The screenshots match `DESIGN.md`: its colours, type, layout, elevation, shapes, components, and its Do's and Don'ts. Name the section a finding breaks.
- The page shows the same rules at each access level (priya, marcus, rosa). A control the account can't use is hidden or disabled, as the access rules say.
- Layout at 390 px: no overflow, nothing clipped, and the touch targets are usable.
- States: empty, loading, error, long text, many rows.
- Keyboard and focus: a reachable order, a visible focus ring, focus goes back to the opener when a dialog or sheet closes, and `aria-current` is right on nav entries.
- The list stays in place when its rows change. The words on the page are plain and use the glossary's terms.

## Plan

- The format follows `docs/directives/plans.md`: phases of checkbox slices, a commit per phase, the open question first, and `## Decisions` holding each choice and why.
- Each slice can be checked on its own, and the order lets the work stop safely after any phase.
- A one-way door (a migration, a public API, a removed route) is named as one, with its rollback.
- The plan matches the issue's Definition of Done, and each item there has a slice that proves it.

## Architecture decision

- The options and their trade-offs, and whether the choice is easy or hard to undo. A choice that is hard to undo needs an ADR in the repo's format (`docs/adr/`, status proposed until the user says yes).
- It does not reopen a question an ADR has settled, unless the decision says so.
- Where the code lives (kernel, foundation or feature) and which way the dependencies run.
- Fitness: how a check, a lint rule or a test would catch drift later.

## Feature idea

- Who uses it (which accounts and access levels) and the problem it solves for them, in the glossary's words.
- The smallest first slice that is useful, and what can wait.
- The data it needs, and whether that means a migration.
- Which module owns it, or whether it needs a new one (`add-module`).
- Its risks: access, production data, CI time, and the work it adds to an upgrade.

## Other implementation detail

- The simplest version that meets the yardstick, and the existing code it should reuse.
- What it breaks somewhere else (callers, through CodeGraph's blast radius).

## PR description

The repo's PR template ends with `## Checklist`, and the attribution line comes after that. Put `## Council review` after `## Checklist` and before the attribution line.
