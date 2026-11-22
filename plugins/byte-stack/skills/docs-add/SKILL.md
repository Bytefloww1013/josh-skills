---
name: docs-add
description: Add a doc to bphs-connect's docs system - a how-to, directive or reference in docs/, or the doc for a skill in .claude/skills/ or a plugin - in the right folder, with its header, after checking the repo doesn't already cover it. Use when a procedure, rule, fact or skill has no doc yet.
argument-hint: "how-to <topic> | directive <topic> | reference <topic> | skill <name> [--repo <owner/name>] [--install \"<command>\"]"
disable-model-invocation: false
---

# /byte-stack:docs-add

Arguments: $ARGUMENTS

Run this only with the user's permission, since it adds a doc to the repo. Implied permission is enough when evidence or precedent
supports it, such as the user asking for this doc, or for the skill, rule or procedure it documents, or approving the same run
before. Say in the reply which it was.

The arguments, with examples, are in `docs/skills/byte-stack.md`. How every doc is written is in
`docs/directives/writing-docs.md`; read it first. This skill holds no rules of its own.

## Step 1 - Read the arguments

| Type | Folder | It holds |
| --- | --- | --- |
| `how-to <topic>` | `docs/how-to/` | numbered steps, each with what success looks like, and `## Guidance` |
| `directive <topic>` | `docs/directives/` | `## Rules`, each ending in `[enforced: <path>]` or `[judgment]`, and `## Guidance` |
| `reference <topic>` | `docs/references/` | facts and one-way-door decisions, each backed by a file and a symbol |
| `skill <name>` | `docs/skills/` | the five sections below, for `.claude/skills/<name>/` or a plugin `.claude/settings.json` turns on |

`--repo <owner/name>` and `--install "<command>"` go with `skill` only. Anything else: stop and show the argument hint.

## Step 2 - Is it needed?

1. Read `docs/README.md` (what each folder holds, and every doc's description) and the docs already in the type's folder.
2. Search the docs for the topic's key words.
3. Draft the doc in the scratchpad, and run `bun run docs:dupes` with the draft copied into the folder; delete the copy straight
   after. A command the draft shares with another doc, or a near-identical sentence, means that fact already has a home.

Stop, say why with `file:line` examples, and wait for the user to confirm before going on, when:
- the repo already covers it (link to the home instead, or add to that doc);
- it isn't needed (one sentence in an existing doc would do);
- it doesn't fit the type (a rule written as steps, a procedure written as facts).

## Step 3 - Write it

1. Put it at `<folder>/<name>.md`, a short lower-case name joined with `-`.
2. Start it with the header: `description` (one line on what it is for), `sources` (the files it describes; never empty) and
   `enforced-by` (a directive: the union of its rule tags; any other doc: the checks that enforce it, or `[]`).
3. By type:
   - `how-to`: a first paragraph of 40 words or fewer, then numbered steps. A step that can't be undone gets a `**Stop:**` line
     asking for the operator's go-ahead. Each step ends with what success looks like ("Expect …").
   - `directive`: each rule tagged. A rule no script can check is `[judgment]`; advice that is neither goes under `## Guidance`.
   - `reference`: refuse any claim you can't back with a file and a symbol (never a line number). Leave it out and tell the user.
   - `skill`: these `##` sections, in order:
     - **What it does and when it's used**
     - **Install**: for a skill listed in `skills-lock.json`, `npx skills add <source> --skill <name> -a claude-code --copy` with
       its `source` there (or `--repo`); `--install` replaces the whole line. For a skill written in this repo, "In this repo, no
       install."
     - **Run**: how to start it (`/<name> …`), and what it needs (tools, logins).
     - **Arguments**: every argument in the skill's `argument-hint`, each with what it does and an example. "None" if it has no hint.
     - **Gotchas**
4. Run `bun run docs:gen` (it adds the doc to the list in `docs/README.md` and to the index in `README.md`), then
   `bun run docs:check`, and the type's own checks: `bun run docs:safety` and `bun run docs:steps` for a how-to. Fix what they
   report. A doc in a folder the README's index has no group for fails `docs:gen`: add the group, with its label, to
   `README_INDEX` in `scripts/docs/generated.ts`.

Then show the user the new doc's path and what it covers. Commit only when the user asks.

## Gotchas

- A new doc of a type that exists is an ordinary change. A new type or folder changes the docs system itself, which goes in a PR of
  its own (`docs/directives/git-and-prs.md`).
- A module's rules go in its own `README.md`, not in `docs/`.
