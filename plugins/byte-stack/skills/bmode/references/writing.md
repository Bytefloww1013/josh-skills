# Writing and lint

Use this reference before you write a doc, a skill, AGENTS.md or CLAUDE.md, a PR body or a commit, and before you change lint or format config. The reply itself follows `SKILL.md` (Writing the reply).

## Docs

`docs/directives/writing-docs.md` is the rule. In short:

- A fact, rule or procedure has one home, and everywhere else links to it.
- A shell command is written in one doc only (`scripts/docs-dupes.ts`).
- A doc stands on its own.
- Use clear words: short sentences, the plain word over the technical one, and no history of how the doc came to be.
- Use the glossary's word (`bun run docs:terms`).
- A reference backs each claim with a file and a symbol, never a line number.
- Change a generated doc through its source and `bun run docs:gen`, never by hand.
- Also write a doc by the `byte-stack:technical-writing` helper, in the mode its folder holds: `docs/how-to/` is how-to, `docs/references/` is reference, and an ADR is explanation. Where the helper and the directive differ, the directive wins.

## Agent-facing text

For skills, AGENTS.md and CLAUDE.md, use the `writing-for-agents` skill:

- One trigger per branch.
- One source of truth per meaning.
- Check every line for relevance, and delete a no-op sentence whole.
- State the target behavior rather than a prohibition.

## PR body

- Draft it in `tmp/pr-body.md` with the sections of `.github/pull_request_template.md`:
  - `## What and why`
  - `## How it was checked`
  - `## Docs unaffected`
  - `## Merge Danger`: `**Door:**` one-way or two-way and why, and `**Blast Radius:**` what a wrong change reaches.
  - `## Checklist`
- The title is a Conventional Commit, `<type>(<scope>): <subject>`, with the type its branch's descriptor maps to. It becomes the commit on `main` and decides the next version.
- The prose follows the `byte-stack:technical-writing` helper's rule for PR descriptions.
- The steps are in the Opening a PR playbook ([../playbooks/opening-a-pr.md](../playbooks/opening-a-pr.md)).

## Commits

Commit subjects on a branch follow Conventional Commits too.

## Comments and lint

- `bun run lint` must exit 0 with no warnings. Turn a noisy Oxlint rule off in `.oxlintrc.json` with a one-line reason, never with `oxlint-disable` comments.
- `no-console` is an error. It is off for server code (`server/**`, `foundation/*/server/**`, `modules/*/server/**`), where the server has no logger and `console` is its log. It is also off for `scripts/**` and for `web/src/lib/submit.ts`.
- `docs/**` is in both the Oxfmt and Oxlint ignore lists, so check `docs/verify/*.mjs` with `node --check` and by running them.
- Markdown and generated files are in Oxfmt's `ignorePatterns`, so do not format them by hand.
- A workaround that needs a paragraph-long comment to justify it means the code is wrong, so fix the code.
