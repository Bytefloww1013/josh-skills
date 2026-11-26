---
name: docs-review
description: Review this repo's docs against the code they describe, through a finder agent, a quote check and a refuter agent, and post what survives as a PR comment (pr) or a docs-drift issue (full). Use before merging a PR that changes code a doc describes, and before each production upgrade.
argument-hint: "pr [<PR number>] | full [<folder>] [--base <ref>] [--no-post]"
disable-model-invocation: false
---

# /byte-stack:docs-review

Arguments: $ARGUMENTS

Run this only with the user's permission, since it can post a PR comment (`pr`) or open a `docs-drift` issue (`full`). Implied
permission is enough when evidence or precedent supports it, such as the user asking for a docs review of this PR, or approving the
same run before. Say in the reply which it was. With `--no-post` it posts nothing, whatever the permission.

The arguments, with examples, are in `docs/skills/byte-stack.md`. The rules the docs are held to are in
`docs/directives/writing-docs.md`; this skill adds none of its own.

**Starting an agent.** Outside T3 Code, launch each agent below by name (Agent tool, `subagent_type`); its definition in
`.claude/agents/` sets its tools and model, so pass no `model`. Under T3 (the `mcp__t3-code__*` tools exist), both agents are
reviewers in `docs/agents/sub-agent-choice.md`: run each on the first model the policy's reviewer list gives, non-critical unless
the reviewed PR's issue is labelled `one-way-door`, and start it as bmode's `references/t3-model-routing.md` says. Its brief comes
from `python3 -I <skill>/../bmode/references/briefs/fill-brief.py <template> --provider <provider> --values <file.json> --out <brief.md>`
(`<skill>` is this skill's base directory; run it from the checkout root; `--keys <template>` lists the inputs), and its report, saved to a file, must pass
`python3 -I <skill>/../bmode/references/briefs/check-report.py <template> <report.md>`.

## Step 1 - Read the arguments

- `pr [<PR number>]`: the docs a PR touches. With no number, the current branch's PR (`gh pr view`); if the branch has none, use
  `--base` instead (default `origin/main`).
- `full [<folder>]`: every doc, or only those under one folder (`full docs/how-to`).
- `--base <ref>`: compare with this ref instead of the PR's base, when there is no PR yet.
- `--no-post`: print the summary and findings here; post nothing.

Anything else: stop and show the argument hint.

## Step 2 - The script checks first

Run these and stop at the first that fails. Report its output: a finding the scripts can make is never left to an agent.

```bash
bun run docs:check && bun run docs:stale && bun run docs:safety && bun run docs:steps && bun run docs:dupes && bun run names:check && bun run scripts:help-check && bun run docs:terms --strict
```

`bun run docs:terms --strict` fails on a glossary wrong word in a doc's prose or a UI string, as CI does.

## Step 3 - Build the bundle

Write it to the session's scratchpad (`$SCRATCH` below), never into the repo:

- `pr`: `bun run docs:review-bundle --pr <n> > $SCRATCH/bundle.json` (or `--base <ref>` with no PR)
- `full`: `bun run docs:review-bundle --all [--folder <folder>] > $SCRATCH/bundle.json`

The bundle reads the docs from the working tree, so for another branch's PR check that branch out first (`gh pr checkout <n>`). If
it lists no docs, say so and stop: nothing to review.

## Step 4 - The finder

Launch one `byte-docs-review-finder` agent with the bundle's path and the scratchpad path. For a large bundle (over about 25 docs),
split the docs between two or three finders by folder; never give two of them the same doc. Each writes its findings to
`$SCRATCH/findings-<n>.json`. Merge them into `$SCRATCH/findings.json`. Under T3, the template is `docs-review-finder`, with
`RUN_DIR` set to `$SCRATCH` and one `--out` per finder.

## Step 5 - The quote check

```bash
bun run docs:quote-check $SCRATCH/findings.json > $SCRATCH/quoted.json
```

Keep its stderr line: how many it kept and why it dropped the rest.

## Step 6 - The refuter

Launch one fresh `byte-docs-review-refuter` agent with, for each finding the quote check kept, only its `doc` and `code` quotes and
locations. Never pass the finder's `why`, its reasoning or this conversation. It answers `upheld` or `refuted` per finding, with the
evidence. Keep the upheld ones, with the finder's `why`, in `$SCRATCH/posted.json`. Under T3, the template is
`docs-review-refuter`, with `FINDINGS` set to `$SCRATCH/quoted.json` (the filler passes on only each finding's quotes and places)
and `RUN_DIR` set to an empty folder of its own, such as `$SCRATCH/refute`. A verdict list shorter or longer than `quoted.json` is a failed report.

## Step 7 - Post

The summary line, filled from the steps above (`n/a` where a number isn't reported, such as tokens when the Agent results give none):

```text
docs-review: <docs> docs reviewed, <raised> findings raised, <quote> dropped by the quote check, <refuted> dropped by the refuter, <posted> posted, <tokens> tokens used
```

The post is the summary line, a table of the findings (doc `file:line`, code `file:line`, why, cause), then the hidden marker and the
findings as JSON, exactly as `scripts/docs/findings.ts` reads them:

````markdown
<!-- docs-review:findings -->
```json
{ "summary": "<the summary line>", "findings": [ ... ] }
```
````

- `pr`: `gh pr comment <n> --body-file $SCRATCH/post.md`.
- `full`: `gh issue create --label docs-drift --title "Docs drift: full review <YYYY-MM-DD>" --body-file $SCRATCH/post.md`.
- `--no-post`, or no findings left: print the post here instead. A `full` review with no findings opens no issue.

Then tell the user the summary line and where it was posted. Fix nothing yourself unless the user asks: the findings are theirs to
act on.

## Gotchas

- The quote check needs exact text. Finders copy quotes from the bundle's numbered text (without the number and tab) and from the
  code files, never from memory.
- A finding about a generated doc (`docs/references/commands.md`, `api-errors.md`, `env-vars.md`) is a `docs:check` matter: the bundle
  leaves them out.
- `bun run docs:drift-report` reads every post this skill makes, so keep the marker and JSON exactly as above.
