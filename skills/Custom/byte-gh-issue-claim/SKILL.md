---
name: byte-gh-issue-claim
description: Work a GitHub issue end to end the ByteFlow way - branch from the issue title, answer the grilling questions from the issue and ask only for the gaps, write a phased checkbox plan, keep issue notes in CLAUDE.md/AGENTS.md, fan out file-owning subagents, commit per phase with Conventional Commits on the issue's branch only, verify with tests/smokes/CI checks and an agent-run visual check, clean up, then squash and open a PR, merge it only when the user says to, and delete the local branch once merged. --verify has the user confirm the manual checks; --auto hands every choice to a Decision subagent.
argument-hint: "<issue number or URL> [--verify] [--auto]"
disable-model-invocation: true
---

# /byte-gh-issue-claim

Issue: $ARGUMENTS

Follow the steps in order. Never skip a **gate**: each one goes to the user, or to the Decision subagent under `--auto` (see Flags). The user's choice is final once they say they want to keep it.

Bundled files (use them, don't rewrite them):
- `${CLAUDE_SKILL_DIR}/scripts/issue-context.(ps1|sh) <issue>` - issue title, bracket tag, labels, body, comments
- `${CLAUDE_SKILL_DIR}/scripts/check-branch.(ps1|sh) <branch> <issue#>` - branch name format and words
- `${CLAUDE_SKILL_DIR}/scripts/guard-branch.(ps1|sh) <branch> <issue#> [base]` - HEAD is on the issue's branch and not on `<base>`
- `${CLAUDE_SKILL_DIR}/scripts/check-plan.(ps1|sh) <plan.md>` - Decisions/Ownership present, unchecked slices, next slice
- `${CLAUDE_SKILL_DIR}/scripts/check-agentsmd.(ps1|sh) <file> <issue#> [active|clean]` - issue block present with all 5 sections, or fully removed
- `${CLAUDE_SKILL_DIR}/templates/` - `implementation.md`, `issue-block.md`

Script runner: on Windows run `pwsh -NoProfile -File <script>.ps1`; on macOS/Linux run `bash <script>.sh`. Every script prints one `PASS:`/`FAIL:`/`WARN:`/`INFO:` line per check and exits 0 (all pass) or 1 (any FAIL).

Names used below:
- `N` - issue number. `<base>` - the repo's default branch (`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`).
- `<branch>` - the issue's branch, made in Step 1 or resumed in Step 0. The only branch this skill commits to or pushes.
- **Branch guard** - run `guard-branch <branch> <N> <base>` right before every `git commit` and `git push`. On FAIL, don't commit or push: switch back to `<branch>` if the tree allows it, else stop and tell the user. Never commit to or push `<base>` or any other branch.
- Plan: `./temp-gh-issue<N>-implementation.md` in the repo root. It is a working file: add it to `.git/info/exclude` so it is never committed.
- Instructions file: `CLAUDE.md` or `AGENTS.md` at the repo root, whichever exists. If both exist and one only imports the other (e.g. `@AGENTS.md`), edit the real one.
- Descriptor -> Conventional Commits type: `feature` -> `feat`, `bug` -> `fix`, `refactor` -> `refactor`, `doc` -> `docs`, `chore` -> `chore`, `test` -> `test`, `ci` -> `ci`. `<type>` below is the one the branch's descriptor maps to.
- Actions: `add`, `build`, `change`, `delete`, `fix`, `install`, `move`, `remove`, `rename`, `update`, `upgrade`.
- If the repo documents its own descriptors, actions or commit rules (a git or PR directive, a names check), those win over the lists above.

## Flags

The issue is the first word of `$ARGUMENTS` that isn't a flag. Flags come in any order and combine. Record them in the plan's Decisions; on a resume, the flags given now win.

| Flags | Gates go to | Manual DoD items |
|---|---|---|
| none | the user | the agent's visual check |
| `--verify` | the user | the user confirms each |
| `--auto` | the Decision subagent | the agent's visual check |
| `--auto --verify` | the Decision subagent | the user confirms each (the run waits for them in Step 7) |

### Visual check (Manual DoD items, without `--verify`)

For each Manual DoD item, test it yourself in depth in a browser against the repo's scratch or dev server, seeded with throwaway data (never production or real data):
- Every state the item names (empty, filled, error, loading, each role, narrow and wide viewports): a screenshot of each.
- The keyboard path: Tab order, Enter/Escape/Space, focus visible on each stop, and where focus lands after a dialog or menu closes.
- Console errors and failed requests during the walk.
- Show each screenshot in chat (read it back as an image) with one `PASS:`/`FAIL:` line per item and what was checked. A FAIL is a failure like any other (Step 7). An item a browser can't check (a wording judgment, a production action): check it the closest safe way, and say what that couldn't cover.

The user isn't asked to confirm these items.

### Decision subagent (`--auto`)

At each **gate**, don't ask the user: spawn one Decision subagent (Agent tool, fresh context; one per question, a batch's questions in one message). Its brief:
- The question, every option with its pros/cons and your recommended one, the issue URL, and the plan's Decisions so far.
- *Read the repo's directives and docs, the instructions file, the user's memory files if any, and the precedent (`git log`, merged PRs, closed issues). Pick the option that best fits best practice, those conventions and what the user would most likely have chosen. Never pick a `one-way-door` option: one that is hard to walk back once done, such as a schema or data migration, deleting anything this run didn't make, a public API change, pushing to or merging into `<base>`, a force push without the lease, sending or publishing anything outside the repo, or touching production or a backup. When unsure whether an option is one, treat it as one. Pick only from the options given. Read only: no edits, commits, pushes or comments.*
- *Reply in exactly this form:* `DECISION: <option>` / `OPTIONS: <each option, one line, one-way-door ones marked>` / `PROOF: <the rule, file:line or precedent (commit, PR, issue) it rests on>` - or `STOP: every option is a one-way-door`.

Print each reply in chat, verbatim, under `### Decision: <gate>`, before acting on it, and add one line per decision to the plan's Decisions (`Auto decisions`). On `STOP`, stop the run and ask the user, with the same options. A Guardrail is the user's, so no decision can waive one.

---

## Step 0 - Preflight

1. `gh auth status` must pass. If not, stop and ask the user to run `gh auth login` (also under `--auto`).
2. `git status --porcelain` must be empty. If not, **gate**: stash, commit, or abort. Never discard the user's changes.
3. Look for `./temp-gh-issue<N>-implementation.md` and a local/remote branch matching `*/*-issue<N>-*`. If found, run `check-plan` and **gate**: **resume** at the first unchecked slice (check out the branch, skip to Step 5) or **start fresh**.

## Step 1 - Read the issue + branch

1. Run `issue-context <issue>`. Read the body, every comment, labels, linked PRs (`gh issue develop --list <N>`, `gh pr list --search "<N>"`) and any files or code the issue points at.
2. Build the branch name: `<descriptor>/<action>-issue<N>-<description>`
   - `<descriptor>` = the word in the title's brackets, lowercased (`[BUG]` -> `bug`; `[DOCS]` -> `doc`). No brackets, or a word that is not a descriptor: use the first matching label (`bug` -> `bug`, `feature`/`enhancement` -> `feature`, `documentation`/`docs` -> `doc`, `refactor`, `chore`, `test`, `ci`), else **gate**: which descriptor.
   - `<action>` = the title's first word after the brackets, lowercased, when it is an action. Otherwise pick the action that fits the change (`Implement` -> `build`, `Allow` -> `add`) and say which.
   - `<description>` = 2-3 lower-case kebab-case words that condense the rest of the title; drop filler words (the, a, system). Example: `[FEATURE] Build an in-repo docs context system to stop docs drift` (#30) -> `feature/build-issue30-docs-context-system`.
3. Run `check-branch <branch> <N>`. Then:
   `git fetch origin && git switch -c <branch> origin/<base>`
4. Add the plan path to `.git/info/exclude`.

## Step 2 - Grill, issue first

Goal: Task, Guardrails and Definition of Done, each concrete enough to test.

| Part | Must answer |
|---|---|
| **Task** | What changes, for whom, what is explicitly out of scope? For a bug: steps to reproduce, expected vs actual. |
| **Guardrails** | What must not change, what must never be done (send, delete, publish, migrate data), which files/systems are off limits, what needs approval first? |
| **Definition of Done** | Which acceptance criteria, tests, smokes and CI jobs prove it is finished? |

1. Answer every question you can from the issue, its comments and the code. Show the result as a table with a **Source** column: `issue` (quote it), `code` (file:line), `inferred`, or `missing`.
2. **Gate**: ask only about `missing` and `inferred` rows, plus anything the issue contradicts itself on. Use AskUserQuestion, at most 4 questions per batch, recommended answer first with "(Recommended)" and its pros/cons.
3. **Push back once** on a vague, untestable or risky answer with a better alternative. If the user keeps it, record it and move on. Under `--auto`, skip this: the Decision subagent has weighed the alternatives.
4. Split the DoD into **Scripted** (exit code: tests, lint, build, smoke command, endpoint status) and **Manual** (human judgment). Push to turn manual items into scripted ones. For a bug, a test that reproduces it is always a scripted item. Each Manual item names the states and keyboard path its visual check covers (see Flags).
5. Stop when all three parts are testable, or after 3 rounds. List remaining gaps and **gate**: proceed with them recorded as open risks, or keep grilling.
6. Use established terms (leading words) instead of long explanations from here on: "exponential backoff", not "wait longer each retry".

Show a one-screen summary of Task / Guardrails / DoD. **Gate**: approve it.

## Step 3 - Plan

Write `./temp-gh-issue<N>-implementation.md` from `templates/implementation.md`. Skip the deep detail for a trivial issue, but always keep Decisions, Ownership and checkbox slices.
- **Decisions** from Step 2, with the issue URL, branch and flags.
- **Phases** of small slices, one `- [ ]` checkbox per slice. A slice is one reviewable change. Each phase becomes one commit.
- **Ownership** table: every slice gets one owner (`main` or `agent-<x>`) and the files/globs, section or topic it owns. No two owners may share a file. Shared files (lockfiles, manifests, CI config, the instructions file, the plan) belong to `main`.
- The last phase is always "Verify + cleanup".

Run `check-plan` (expect FAIL only for unchecked slices). Show the plan. **Gate**: approve it.

## Step 4 - Issue notes in CLAUDE.md / AGENTS.md

Add an issue block from `templates/issue-block.md` to the instructions file, between the markers `<!-- byte-gh-issue-claim #<N> START -->` and `<!-- byte-gh-issue-claim #<N> END -->`, with these sections:
- **Tools** - commands, scripts, MCP servers needed for this issue that the agent can't guess.
- **Tests** - exact commands to run the relevant tests and smokes, fastest first.
- **CI** - which workflow/jobs gate this change and how to reproduce them locally.
- **Important Information** - the plan path, branch, Guardrails in one line each, key file paths.
- **Gotchas** - traps found in the code or the issue, each with the correct behaviour.

Rules: bullets only, one line each, no code walkthroughs, nothing the agent can read from the code, keep the whole file under 200 lines. Never edit content outside the markers. If neither file exists, **gate**: create `CLAUDE.md`. Show the diff. **Gate**: approve it. Write it, run `check-agentsmd <file> <N> active`.

**Standing rule:** whenever a new command, test trick or repeated mistake comes up, propose a one-line addition to the block (under `--auto`, add it and say so).

## Step 5 - Implement (fan-out)

- Work phase by phase. Inside a phase, run slices with disjoint ownership in parallel with subagents (Agent tool, one call per owner, sent in one message); run the rest yourself.
- Each subagent brief contains: the issue summary, its slices, the **exact files/section/topic it owns**, the Guardrails, the test command, and these rules: *edit only the files you own; if you need a change elsewhere, stop and report it; do not commit, push, or switch branches; report the files you changed and the test output.*
- After each subagent returns, check `git status --porcelain` / `git diff --stat` against its ownership, and that the branch is still `<branch>`. Any file outside it: revert that file and redo the work yourself or reassign it.
- Tick `- [x]` in the plan only when a slice is done and its tests pass.
- Respect Guardrails at every step. If a slice would break one, stop and ask the user (also under `--auto`).

## Step 6 - Commit + push per phase

At the end of each phase:
1. Run the phase's tests. Do not commit a red phase.
2. Stage only the phase's files by path (never the plan file).
3. Run the branch guard. Commit with a Conventional Commits subject: `<type>(<scope>): <subject> (#<N>)` - `<scope>` the module or area the phase touches (lower case, or leave `(<scope>)` out), `<subject>` what the phase does in lower-case imperative words, no trailing period. Example: `feat(maintenance): add the dispatched_to column and migration (#24)`.
4. Run the branch guard, then push: `git push -u origin <branch>`.
5. Run `check-plan`, then review the issue block: add, prune, or leave it.

## Step 7 - Verify

Run everything that proves the issue is fixed, and show the output in chat:
- The tests and smokes listed in the issue block, then the full suite if it runs in reasonable time.
- What CI runs: read `.github/workflows/*` and run the same lint, type-check, build and test commands locally.
- Each acceptance criterion from the issue, and the reproduction steps for a bug (now passing).
- `gh run list --branch <branch> --limit 3` for the phase commits; any failure gets fixed before moving on. Under `--auto`, wait for the last run (`gh run watch <id> --exit-status`).
- Each Manual DoD item: the visual check (see Flags), or with `--verify` ask the user to confirm it.

Any failure: fix it in a new slice, commit it as its own phase, re-run Step 7.

## Step 8 - Cleanup

1. **Gate**: keep any lasting item from the issue block (e.g. a test command that was missing) by moving it into the file's permanent sections. Move only what is approved.
2. Delete the issue block, markers included. Run `check-agentsmd <file> <N> clean`.
3. Run the branch guard. Commit `chore: remove the issue notes (#<N>)`, and push. If the issue block was the only content of a file you created in Step 4, delete the file instead.

## Step 9 - PR

Done means: every Step 7 check passed (CI included), `check-plan` reports 0 unchecked slices, `check-agentsmd ... clean` passes, and every Manual item passed its visual check (or the user confirmed it, with `--verify`). Report that in a few lines, then open the PR without asking. Not Done: stop here and say what is missing.

1. `git fetch origin`. If `<base>` moved, `git rebase origin/<base>` and re-run the Step 7 tests.
2. Squash: `git reset --soft $(git merge-base HEAD origin/<base>)`, then run the branch guard and make one commit:
   `<type>(<scope>): <subject>` - the issue title without the bracket tag, its first word lowercased, no issue number (a squash merge adds the PR number) - with a body of 3-6 bullets summarising the change, and `Closes #<N>`. Example: `feat(maintenance): allow free-text vendors in the "Dispatched to" field`.
3. Run the branch guard, then `git push --force-with-lease -u origin <branch>` (force is required when the phase commits were already pushed; never force without the lease, never any branch but `<branch>`).
4. `gh pr create --base <base> --head <branch> --title "<commit subject>" --body "<summary, test evidence, Closes #<N>>"`. Under `--auto`, the body also lists each Auto decision in one line.
5. Report the PR URL and `gh pr checks <pr>` status. **Gate**: delete the local plan file?
6. Merge only when the user says to; a Decision subagent never stands in for that, even under `--auto`. Once the PR is merged: `git switch <base>`, `git pull`, then `git branch -D <branch>` (`-D`, because a squash merge leaves the branch's commits off `<base>`).
