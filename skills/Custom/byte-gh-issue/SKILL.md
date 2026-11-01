---
name: byte-gh-issue
description: Create a GitHub issue in the current repo with the gh CLI - a typed, verb-first title, a concise Markdown body (Why, Requirements, Changes, General Steps, Definition of Done, References) and fitting existing labels.
argument-hint: "[--grill] <what the issue is about>"
disable-model-invocation: true
---

# /byte-gh-issue

Request: $ARGUMENTS

If the request starts with `--grill`, strip the flag and run Step 1b after Step 1; without it, skip Step 1b.

## Step 1 - Preflight

Run these from the current directory. Stop and tell the user if any fails; never log in or change gh config for them.
- `gh auth status` - uses the credentials already in gh
- `gh repo view --json nameWithOwner,url` - must be inside a GitHub repo
- `gh label list --limit 200 --json name,description` - the only labels you may use

If the request is too vague to fill Why and Requirements, ask one short question first. Read relevant code or docs in the repo only when it makes the issue more accurate.

## Step 1b - Grill (`--grill` only)

Grill the user until the request is one narrow issue: a single problem, a clear in/out scope, the area of the code it touches, and an observable Definition of Done. The step is complete when every section of Step 3's body can be written from the user's answers alone, with no guess left.

1. Read the code, docs and ADRs the request touches (`codegraph_explore` where `.codegraph/` exists). Write the open questions: one decision each, broadest first (what problem, then scope, then area, then behaviour, then done).
2. Spawn the **Decider**: a fresh `general-purpose` agent (never `fork`), description `Decider`, so its context is clean. Its prompt holds only the user's request as written, the question, and the context you gathered for that question (file paths, line ranges, doc and ADR names). Ask it for 2-4 answers, one marked recommended, each recommendation backed by proof: a `path:line` or a quoted doc/ADR line it read. An answer without proof is listed as unbacked and is never the recommendation. Send each later question to the same Decider (`SendMessage`), or spawn a new one given the earlier questions and answers.
3. Open each cited `path:line` and keep only the proof that says what the Decider claims.
4. Ask one question at a time, in chat: the question, then the answers as a numbered list, the recommended one first with `(Recommended)` and its proof. The user picks a number or writes their own answer. End the turn and wait.
5. Accept the answer, or push back with the proof. Each question gets at most two pushbacks:
   - First: the answer conflicts with the code, a doc or the architecture.
   - Second: only for a **one-way door**: the answer risks irreversible harm (data loss, production), changes the architecture (module boundaries, the kernel, a schema), or makes the issue `one-way-door`. Name which.
   - After that, or when the user holds their answer, the user's answer is final. A one-way-door answer kept after the second pushback gives the issue `one-way-door` in Step 4.
6. Once complete, post the interpretation in 2-4 lines and go on to Step 2 when the user says yes.

## Step 2 - Title

`[TYPE] <Action> <specific what and where>`

`/byte-gh-issue-claim` names the branch from the title (`<type>/<action>-issue<N>-<2-3 words>`), so TYPE and Action come only from these lists. If the repo documents its own branch descriptors and actions (a git or PR directive), use its lists instead.

- TYPE, in brackets and all caps, one of: FEATURE (new behaviour), BUG (something broken, including a performance or security fault), REFACTOR (same behaviour, better code), DOC (docs only), CHORE (tooling, dependencies, upkeep), TEST (tests only), CI (pipelines). Research or a spike takes the type of the change it is for.
- Starts with one of these verbs: Add, Build, Change, Delete, Fix, Install, Move, Remove, Rename, Update, Upgrade
- Descriptive, under ~80 characters, no trailing period
- Example: `[FEATURE] Build an in-repo docs context system to stop docs drift` (branch `feature/build-issue30-docs-context-system`)

## Step 3 - Body

Markdown, in this order. Concise: enough to work from, nothing padded. Skip filler like "This issue is about...".

```markdown
## Why
<1-3 sentences: the problem or value, who it affects>

## Requirements
- <must-have behavior or constraint>

## Changes
- <area / file / component> - <what changes>

## General Steps
- [ ] <step>
- [ ] <step>
- [ ] <step>

## Definition of Done
- <observable outcome that proves the issue is complete>

## References
- [<title>](<url>)
```

- General Steps: 3-6 high-level checkboxes, not a full plan
- Definition of Done: what is true once this is finished (behavior, tests passing, docs updated), not a visual description
- References: real links only (docs, related issues/PRs, repo files via the repo URL, pages on the site). Never invent URLs; if there are none, write `- None yet`

## Step 4 - Labels

Every issue gets exactly one of `one-way-door` (hard to walk back once done, such as a schema or data migration, a public API or a deletion) or `two-way-door` (easy to undo). If the repo has neither label, stop and tell the user.

Add any other labels from Step 1 that clearly fit (type, area, priority). Never create labels.

## Step 5 - Create

Write the body to a temp file outside the repo, then:

```
gh issue create --title "<title>" --body-file <temp file> [--label "<a>" --label "<b>"]
```

Delete the temp file. Reply with the issue URL and the title only.
