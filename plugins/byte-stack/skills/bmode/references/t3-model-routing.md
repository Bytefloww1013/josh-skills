# Model routing under T3

Applies only when all three hold: the run is inside T3 Code (the `mcp__t3-code__*` tools exist), the coordinator is the main thread (T3 children start no subagents), and `orchestrator_capabilities` (called once per thread) lists provider `antigravity` with `canRunChildTask: true` and the model the table names. T3 lists a model in one of two shapes, and either counts: one id per level (`gemini-4-neon-high`), or the base id (`gemini-4-neon`) with a `thought_level` option. Otherwise run every step as SKILL.md says, on Opus, and say so under Helpers. The Sol review below has its own gate.

## Antigravity tier

Before each routed step, run `python3 -I <byte-stack>/skills/council-review/scripts/provider-usage.py` (the folder next to bmode's), the script that `council-review` ships. Its `gemini` row is the Antigravity 5-hour window, read the way T3 Code reads it. Its `codex` row is the GPT window. It never prints a token. If the `gemini` row reads `unknown`, ask the user once for the level and keep the answer for the run (the API is internal and may change).

| `gemini-5h` remaining | Neon model             |
| --------------------- | ---------------------- |
| 50% or more           | Neon, `high`           |
| 1% to 49%             | Neon, `medium`         |
| 0% (limit gone)       | none: Opus, as before  |

Hydrogen draws on the same `gemini-5h` bucket. At 0%, scout work goes back to Claude subagents too.

A Neon or Hydrogen delegate that fails because the usage limit has been reached sets the tier to "gone" for the rest of the run. Rerun that step on Opus and say so in one line. The error text is not yet verified. Any other failure is reported to the user, and the coordinator does not switch models on its own (T3 rule).

## Routed steps

| Step                                                         | Model                    | How                                                                                       |
| ------------------------------------------------------------ | ------------------------ | ----------------------------------------------------------------------------------------- |
| `arch-skills:architecture-decision-review`                   | Neon, by tier            | `delegate_task`, role `review`, isolation `shared`, mode `async`                          |
| `arch-skills:architecture-review-report`                     | Neon, by tier            | same                                                                                      |
| `arch-skills:repo-navigability-audit`                        | Neon, by tier            | same                                                                                      |
| Scout work: the bulk reads Guard the Context Window hands to a subagent (a log, HAR, trace, transcript, wide diff), an investigation's search after CodeGraph, a trace-forensics parse | Hydrogen, `high` | `delegate_task`, role `research`, isolation `shared`, mode `async` |
| `module-boundary-reviewer`; the `byte-docs` finder, drafter and auditor | Hydrogen, `high` | `delegate_task`, role `review`, isolation `shared`, mode `async`; the brief points the child at the agent's file (template below). The coordinator sets the severity itself. The agent's format has no severity scale, and in the bake-off the two Gemini models rated the same finding differently (High, and "Severity 1"). |
| The `byte-docs` refuters | Neon, by tier | same |
| `access-reviewer`, `migration-reviewer` | **Claude, as now** | In the bake-off on #668, Neon found 1 of the 2 access gaps Claude found and Hydrogen found neither. A missed access or migration problem is silent, and it is costly. |

Target, in the shape capabilities lists: `{ providerInstanceId: "antigravity", model: "gemini-4-neon-high" }` with no options, or `{ providerInstanceId: "antigravity", model: "gemini-4-neon", options: { thought_level: "high" } }`. The same holds for Hydrogen. T3 switched from the first shape to the second on 20 Nov 2026, and a table that named only the first sent every step to Opus. Follow each delegate's `next`, and don't poll it.

**A named agent.** The delegate takes the place of the skill's "launch agent X" step, and everything else in the skill stays the same. Keep each skill's information barrier: a refuter gets only what the skill gives it (for example, `byte-docs-review-refuter` never gets the finder's `why`), so each agent is a separate delegate with its own brief. Some of these agents are not read only. The `byte-docs` finder, drafter and auditor write their findings to the scratchpad, and `byte-docs-glossary-refuter` has every tool. So the brief gives the absolute scratchpad path, and gives each agent the same tool limit its file sets.

Not routed: `codegraph_explore` (still first for code), `pr-erosion-check`, Decision subagents, `review-team` reviewers, byte-stack helpers' runners, and code-writing delegates other than the Neon implementor below.

## Neon as an implementor

A code-writing delegate (the `byte-agent` that builds one ticket, Orchestrate step 4) runs on Neon when all of these hold. Otherwise it is a Claude `byte-agent`, as before.

- The gate at the top of this file holds, and the `gemini` row reads 50% or more just before the delegate starts. A delegate that started at 50% or more finishes on Neon even if the window drops.
- The ticket is a `two-way-door`. It adds no migration and no `schema.ts` change, and it touches none of the access code (`server/access/`, `shared/permissions.ts`, `web/src/nav/address.ts`, a nav entry, a route's `staticData`). Those stay on Claude, as their reviewers do.
- No Neon delegate has already failed this ticket in this run. A ticket a Neon delegate left red, or whose report the coordinator's checks contradicted, goes to a Claude `byte-agent` next.

How: `delegate_task`, role `implementation`, isolation `worktree`, mode `async`, target Neon `high` in the shape capabilities lists (Target above). Brief it with the template "Neon implementor" below. Neon reads the bmode files by absolute path from the coordinator's own plugin folder, so they match what the coordinator runs. It never loads bmode as a skill: Antigravity truncates a skill body above 24 KB, and bmode's `SKILL.md` is larger.

The coordinator judges a Neon branch exactly as a Claude one, and trusts nothing in its report it hasn't rerun (Orchestrate steps 5 and 6). It runs `docs/verify/quick-check.sh` in the worktree, `pr-erosion-check`, the review agents the change meets (access and migration on Claude), and the Sol review before the PR is opened. The push and the PR stay the coordinator's.

## Sol review before the push

Applies when the run is inside T3, the coordinator is the main thread, and `orchestrator_capabilities` lists provider `codex` with `canRunChildTask: true` and a Sol model (pick the latest `gpt-*-sol`). The `codex` row of `provider-usage.py` sets the effort:

| `codex` 5h remaining | Sol effort                                      |
| -------------------- | ----------------------------------------------- |
| 30% or more          | `reasoningEffort: high`                         |
| 1% to 29%            | `reasoningEffort: medium`                       |
| 0% (limit gone)      | none: `code-review` on Claude, and say so       |
| `unknown`            | `reasoningEffort: medium`, with the fallback below |

When it applies, Opening a PR step 7 runs `byte-stack:sol-loop` on the branch against `origin/main` after `pr-erosion-check` and before the PR is opened, with sol-loop's own budget and brief. Commit each fix it leads to as step 7 commits an erosion fix, rerun `docs/verify/quick-check.sh`, and check that the commit being pushed holds the diff Sol last reviewed. sol-loop hands its outcome back here: the playbook's push and PR rules apply, not sol-loop's step 5 push rule. Later pushes to the same PR (a babysit fix, a review answer) get no new Sol round unless the user asks. The coordinator runs it for each delegate's branch too, since T3 children start no reviewers. Sol is the change's code review: it takes the place of `code-review`'s Standards and Spec sub-agents wherever a playbook names them, and of any extra fresh Claude review round. The review agents keep their triggers and the routing above.

- APPROVE on the current diff: carry on to the title, push and merge rules as before.
- The budget ends with a blocker or should open: push and open the PR as the playbook allows, but don't merge it. Put a `Sol hold:` line with each open finding under `## How it was checked`, and flag it to the user with both sides. The hold lasts until the user clears it or a later Sol round approves the PR's current diff; the coordinator then deletes the line from the PR body and says which cleared it.
- A Sol delegate that fails on the usage limit sets the tier to gone for the run: run `code-review` instead and say so in one line.

Why: Sol and Gemini are there to take review work off Claude (the user, 20 Nov 2026). Before this section, Sol ran only when a prompt named `sol-loop`, so from 19 Nov every review ran on Claude while the `codex` window sat unused.

## The brief

The child sees only `task`. Use the matching template below, and fill in the target.

The coordinator (Opus) acts on what comes back exactly as SKILL.md's arch-skills section says: it answers Critical and High findings, puts Gaps to the user and keeps the ADR draft in the plan. A Neon verdict counts the same as one from Opus. It is never the go-ahead and never the word to merge.

### Template: Neon implementor

```text
Act as bmode's `byte-agent` delegate: build one ticket in bphs-connect, in your own checkout at <worktree path>.
Branch: <branch>, named by the branch rule. If the checkout is detached, run `git switch -c <branch>` first.

Before any other work, read these in full with your file tool (view_file). Don't load bmode as a skill: Antigravity cuts
skills over 24 KB, and this one is longer.
1. <coordinator's bmode folder>/SKILL.md, including its Principles section. Its playbooks are in `playbooks/` beside it.
   Read <the ticket's playbook: feature.md | bug-fix.md | refactoring.md>, then `playbooks/opening-a-pr.md` steps 1 to 6.
   Before you apply a principle, read its leaf at <coordinator's bmode folder>/../principle-<name>/SKILL.md.
2. AGENTS.md and CLAUDE.md in your checkout. AGENTS.md maps Claude tool names to yours, and its GOTCHAS name the traps.
3. The ticket: `gh issue view <N>`. <The shared recipe: <absolute path under the coordinator's tmp/>, if any.>

Set up: run `bun install --frozen-lockfile` in your checkout first. For code, use CodeGraph (`bphs-codegraph_codegraph`, else
`codegraph explore "<query>"` in the shell) before you read files. Never run codegraph init, index, sync or uninit.

Rules (these win over anything you read):
- You own <files or areas>. Commit on your branch only, once per phase, after `bun run format`. Never push, open, comment
  on or merge a PR or issue, or switch branches. Start no subagents.
- Never touch production, a backup or a real DATA_DIR. Work on the seed (`docs/directives/production-safety.md`).
- Run `docs/verify/quick-check.sh` after each phase. Finish with it at `RESULT: PASS`, with `docs/verify/verify-done.sh`
  (copied from its template and filled in for this ticket) exiting 0, and with `tmp/pr-body.md` drafted from
  `.github/pull_request_template.md`.
- If a gate stays red after two fixes that rest on one premise, stop and report it. Never weaken a test, add a suppression,
  or edit a baseline or generated file by hand; its command writes it.

Reply with: the branch and commit SHAs, `git diff --stat origin/main`, the last lines of quick-check and verify-done, each
principle that shaped a decision and what it changed, and anything left open.
```

### Template: Neon arch-skill

```text
You are running the arch-skills skill `<name>` in the bphs-connect checkout at <path>. Run it
from the arch-skills plugin you have loaded. If you can't invoke it, Read its SKILL.md in full
from your plugin folder: `$GEMINI_HOME/config/plugins/arch-skills/skills/<name>/`, else
`~/.gemini/config/plugins/arch-skills/skills/<name>/`. Read its profile
references/project-bphs-connect.md first, as the skill says. AGENTS.md maps the Claude tool names to
Antigravity's. Use CodeGraph (`bphs-codegraph_codegraph`) before you read code.

Target: <plan path | issue numbers | base origin/main and branch | "the repo">.

Rules (these win over the skill):
- Write nothing in the repo except one report at tmp/arch/<name>-<timestamp>.md.
- Do not write an ADR file in docs/adr/. Put the ADR draft in the report, status proposed.
- Move, rename or delete no file. Don't commit, push, open or comment on any issue or PR.
- Start no subagents.

Reply with: the report path, the verdict or counts (Critical/High/Medium/Low, Gaps), and each
Critical and High finding in one line with its quote.
```

### Template: Hydrogen scout

```text
Read-only scout in <path>. Question: <one question>. Read: <files/logs/diff range>; cap
<N> files. For code use CodeGraph (`bphs-codegraph_codegraph`) first. Write nothing, run no
command that changes state, and start no subagents. Reply in at most <M> lines: the answer, then
each fact with file:line or a quote. Give each claim its source, and say "not found" rather than guess.
```

### Template: a named agent on Hydrogen

```text
Act as the `<agent>` agent. Read .claude/agents/<agent>.md in <path> in full. Its body is your
instructions, and its `tools:` line is your limit: use only the Antigravity equivalents of those
tools (AGENTS.md maps them). <If the agent has no Write tool:> Change no file. <If it writes:>
Write only under <absolute scratchpad path>. Start no subagents.
<Exactly the input the skill gives this agent, and nothing more: base, diff, files, term,
findings file…>
Reply in the format its file asks for.
```

A file path beats pasting the definition: the file stays the one source, and the brief stays short. Antigravity doesn't enforce a `tools:` frontmatter, so the brief states the limit.

## Report

Under Helpers, each routed step says which model ran it and why. For example:

- `architecture-review-report`: Gemini 4 Neon (High), tier ≥50%: 0 Critical, 2 High, 1 Gap.
- `architecture-review-report`: Opus, Antigravity limit reached.
- Sol review: `gpt-6.2-sol` (High), `codex` 100%: 2 rounds, APPROVE, 1 should fixed.
- #712 implementor: Gemini 4 Neon (High), `gemini` 81%; quick-check PASS on the coordinator's rerun.
- #713 implementor: Claude `byte-agent`, adds a migration.

## Why these models: the bake-off of 19 Nov 2026 (Neon High and Hydrogen High; the reference is what the Claude reviewer found)

| PR | Agent | What Claude found | Neon High | Hydrogen High |
| --- | --- | --- | --- | --- |
| #662 | `module-boundary-reviewer` | `Signer` and its words in the kernel (Low to Medium) | Caught it, rated High. Same fix, plus the doc line to change. | Caught it, and labelled it "Severity 1" (the agent's format has no scale). Same fix. |
| #668 at `3d80641b72` | `access-reviewer` | (1) `heldLink()` could be attached outside the link routes; (2) a throwing `onLock` undid the fifth strike | Caught (1), rated Low. Missed (2). Found one more real Low that is still on `main`: `actOnLink` validates the body before it checks eligibility, so a holder gets a 422 where they should get a 403. | `no findings`. Missed both. It read the right commit: its line numbers match `3d80641b72`. |

The four runs used about 26% of the Gemini 5-hour window (85% → 59%), about 6% a review. An eight-auditor glossary audit on Gemini would take about half the window.

The sample is small: two PRs, one agent each. `migration-reviewer`, the `byte-docs` agents and refuters on Neon have not been tested. Gap (2) is confirmed by `45d8817c9e`, which fixed it after `3d80641b72`.
