# Dispatch loop: scout, implementor, reviewer

The coordinator is the main thread under bmode. It plans, fills a brief for each delegate, checks each report and routes the next step. It stays in the main thread: byte-stack's T3 routing has children start no subagents, so the loop lives with whoever holds the Agent tool or `delegate_task`. The Orchestrate playbook decides when this loop runs; this file is how one task moves through it. The briefs and their scripts are in `briefs/` beside this file.

## Before the first dispatch

1. **Hold the user's gates.** A plan is built only after the user's go-ahead. A PR opens only on the user's say-so, a merge only on the user's word, and nothing is pushed to `main` (`docs/directives/git-and-prs.md`). A `**Stop:**` step runs only on the operator's go-ahead (`docs/directives/production-safety.md`).
2. **One run folder per task.** Make `<coordinator checkout>/tmp/agents/<task-id>/`, and give each delegate run its own subfolder (`scout-1`, `impl-1`, `review-1`) as its `RUN_DIR`. Use the absolute path: `tmp/` is git-ignored, so a worktree doesn't have it.
3. **Pick the model.** bphs-connect's `docs/agents/sub-agent-choice.md` is the policy: the model and level per role, tried in order, by whether the job is critical. Under T3, `t3-model-routing.md` says how to read the usage left and start each delegate.
4. **Pin the base.** `git fetch origin && git rev-parse origin/main` gives `BASE_SHA`. Name the branch by the branch rule. Neither `delegate_task` nor the Agent tool can start a child in an existing worktree. So before a fix pass on the same branch (`PASS_WITH_CHANGES`, `BLOCKING`, or a retry after `BLOCKED` for missing context or a wrong base): copy the old worktree's git-ignored files (`docs/verify/verify-done.sh`, `tmp/pr-body.md`, the plan copy) into `<RUN_DIR of that run>/carry/` at their relative paths, run `git worktree remove <old worktree>`, and fill the next brief with `START=continue`, `EXPECTED_HEAD` set to the branch's head and `CARRY_DIR` set to that folder. A red branch is not continued: it moves to the next model with `START=new`, after the failed worktree is kept as `t3-model-routing.md`'s When an implementor fails says.
5. **Fill the brief with `python3 -I <bmode>/references/briefs/fill-brief.py <role> --provider <provider> --values <file.json>`**, never by hand. `--keys <role>` lists what each placeholder takes. Pass the printed brief as the delegate's whole task. It inlines the shared rules, writes the CodeGraph line for the delegate's provider, and refuses a brief with a placeholder left.

## Where to start

- The code involved is unknown or only partly known: **scout**.
- A review of an existing branch or PR: **reviewer**, after a scout if the area is unmapped.
- Files, symbols and spec are already proven: **implementor**.

## Check every report

Save it as `<RUN_DIR>/report.md` and run `python3 -I <bmode>/references/briefs/check-report.py <role> <RUN_DIR>/report.md`. It fails a report that misses a section, a status or verdict value, or a `path:line` place. On a fail, send the same role one more run with the list of what was missing. Then judge the work, not the report: rerun `docs/verify/quick-check.sh` in the implementor's worktree and read `git diff --stat origin/main` against what it owns.

## Routing

**After a scout**

| Report | Next |
| --- | --- |
| `COMPLETE` | Write the spec from its evidence; send an implementor (or a reviewer, for a review-only task). |
| `GAPS` on a fact the next step needs | One more scout with narrower questions. Still open after the second: ask the user. |

**After an implementor**

| Report | Next |
| --- | --- |
| `DONE` | Review gates below. |
| `BLOCKED`, missing context | A scout with the exact question; update the spec and owned files; a fresh implementor. |
| `BLOCKED`, base or branch wrong | Recheck `origin/main`. If the new base is safe, a fresh implementor on it; else ask the user. |
| `BLOCKED`, red after two fixes, or a report the checks contradict | Under T3, the next model in the policy's list builds the ticket afresh (`t3-model-routing.md`, When an implementor fails). With no model left, or outside T3: stop, and give the user the output and the blocker. |
| `BLOCKED`, the spec fights the code | Stop. Give the user the blocker. |

**Review gates (every `DONE` branch, before the push)**

1. `arch-skills:pr-erosion-check` against `origin/main`, with the issue as the yardstick.
2. Each review agent bmode's Review agents rule triggers, on the reviewer model the policy picks.
3. The reviewer brief, or under T3 the Sol review, which stands in for it.

**After a reviewer**

| Verdict | Next |
| --- | --- |
| `PASS` | Push the branch. Open the PR only on the user's say-so. |
| `PASS_WITH_CHANGES` | A fresh implementor, fix pass, with the findings as its spec. When it returns `DONE` with checks green, rerun the erosion check on the new diff, and each review agent whose ground the fix touches. No second reviewer-brief round. Under T3, sol-loop's rule governs instead: the pushed commit must hold the diff Sol last reviewed. |
| `BLOCKING` | A fresh implementor with every `Critical` and `High` finding, then a fresh reviewer. After the second `BLOCKING`: ask the user. |
| `NEEDS_INVESTIGATION` | A scout with the reviewer's Gaps, then a fresh reviewer given the scout report. |

## Limits

- Two scouts per open question.
- Two `BLOCKING` rounds per task.
- One fresh implementor after `BLOCKED` for missing context or a wrong base, and only once the blocker is gone; a red branch moves down the policy's list instead.

At a limit, stop and give the user the evidence.

## Reply to the user

Lay out the result as the Orchestrate playbook's Reply line asks: what landed, each issue and PR with its link, live checks and the erosion verdict, what was dropped and why, and what waits on the user. Add a dispatch log:

| Step | Role | Model and level | Status or verdict | One-line takeaway |
| --- | --- | --- | --- | --- |
