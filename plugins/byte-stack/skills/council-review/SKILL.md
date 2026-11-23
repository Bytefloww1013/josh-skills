---
name: council-review
description: Gets a rigorous, scored review from a council of three models from three providers (Claude Opus 5.5, Gemini 4 Neon, GPT-6.2 Sol), with DeepSeek V4.1 Flash as the fallback seat, and repeats it after fixes until every seat is satisfied. Reviews code (a PR, branch or diff), UI changes from screenshots, plans, architecture decisions, feature ideas and other implementation details. Use only when the user says "council" or asks for a council review. Never start it yourself, and never as a routine step before a PR.
---

# Council review

A council is three reviewers from three providers who review the same thing independently. You are the coordinator. You build the packet, start the seats, check what they find, fix what holds up, and run the next round.

Only the user starts a council. It is extra insurance for when the user is not sure of the direction, so it costs three providers' quota for each round. Never start it yourself: not for every PR, not from a playbook step and not because a change looks risky. When a change looks like it needs one, you may suggest it in one line, and the user decides.

## 1. Before the council

- Address open PR comments, fix the issues you already know about and run the relevant checks first. Give the council the updated implementation. Do not hold back known fixes until the reviews return.
- If the user wants to discard the implementation and explore new ideas, skip the fixes to code that is going away.
- Name the yardstick: the issue, the plan or the user's request. Every seat reviews against it.
- In a repo that has a profile in `references/` (`project-<repo>.md`), read it now. Its checks and criteria apply on top of this file, and the repo's own rules win over this skill.

## 2. Pick the kind and build the packet

One council reviews one thing. Pick its kind:

| Kind | The packet holds |
| --- | --- |
| Code | The base and head SHAs, `git diff --stat`, the yardstick, the checks you ran and their results. Seats read the diff themselves. |
| UI change | Screenshots before and after at each width and account the profile names, each with its address, plus the code diff. Give the absolute PNG paths. |
| Plan | The plan's absolute path or full text, the yardstick and what the plan may not change. |
| Architecture decision | The options, the constraints, the decision being proposed and how hard it is to undo. |
| Feature idea | The problem, who it is for, the ideas so far and the limits (time, data, access, cost). |
| Other implementation detail | The question, the code it touches (paths or SHAs) and the options. |

For a UI change, take the screenshots before the council starts. DeepSeek cannot see images. When it fills a seat on a UI change, it reviews the code diff only, and the report marks that seat `code only`.

## 3. Seats

| Seat | Default | By 5-hour usage left | When the seat is down |
| --- | --- | --- | --- |
| Claude | Opus 5.5, High | - | DeepSeek |
| Gemini | Gemini 4 Neon, High | 50% or more: Neon `high`. 20% to 49%: Neon `medium`. Under 20%: Hydrogen `high`. 0%: DeepSeek. | DeepSeek |
| GPT | GPT-6.2 Sol, High | 50% or more: `reasoningEffort: high`. Under 50%: `medium`. 0%: DeepSeek. | DeepSeek |
| Fallback | DeepSeek V4.1 Flash Free (`opencode/deepseek-v4.1-flash-free`), `variant: max` | - | - |

- If the user names the council's members, use those. When a member the user named is down, report it and do not substitute. The fallback below is only for the default seats.
- Take the model ids from `orchestrator_capabilities`. When the id in the table is no longer offered, that seat is down. Tell the user which ids are offered now, so the table can be updated.
- Read the usage with `python3 -I <this skill>/scripts/provider-usage.py`, before round 1 and again before each later round. It prints a percent left for `codex` (5-hour window) and for each Antigravity account: `gemini` (`antigravity`) and `gemini:antigravity_2`, each the tighter of its 5-hour and weekly windows. The Gemini seat runs on whichever account has more usage left (on a tie, `antigravity`), re-picked before each round, and on the other account with the same model when that one hits a limit; it is down only when both are. When a row reads `unknown`, use the seat's default and rely on the fallback below.
- A seat is down when its usage is 0%, when its provider or model is not offered, or when its delegate fails on a usage limit or cannot connect. Then that seat's round runs on DeepSeek, and the report says which seat fell back and why. Report any other failure to the user, and do not swap that seat.
- These fallbacks are the user's standing instructions. Make no other substitution. If two or more seats are down in one round, tell the user that the council has lost provider diversity before you score that round.
- Antigravity's usage-limit text (seen 23 Nov 2026): `Individual quota reached. Please upgrade your subscription to increase your limits. Resets in <h>h<m>m<s>s.` (HTTP 429). `⚠ Verification Required` (HTTP 403) means the user must verify that account: try the other account, and tell the user.
- Images: Claude, Gemini and GPT read the PNG files. DeepSeek V4.1 Flash is treated as text only (see section 2).
- Cost: a full Gemini review used about 6% of the Gemini 5-hour window in testing. Read the usage before each round, not once per run.

How to start each seat:

- **In T3 Code:** call `orchestrator_capabilities` once per thread. Start every seat with `delegate_task`, `mode: async`, `role: review`, `isolation: shared`, all in one message so they run in parallel. Use these targets:
  - Claude: `claudeAgent`, `claude-opus-5-5`, `{effort: high}`. When the coordinator is itself Claude, use the native `Agent` tool instead (`model: opus`, effort high, `run_in_background: false`), as T3 asks for a same-provider child.
  - Gemini: the Antigravity account with more usage left (`antigravity` or `antigravity_2`, as above), with the model and level from the table, in the shape capabilities lists: an id per level (`gemini-4-neon-high`), or the base id (`gemini-4-neon`) with `options: { thought_level: "high" }`.
  - GPT: `codex`, `gpt-6.2-sol`, `{reasoningEffort: high|medium}`.
  - DeepSeek: `opencode`, `opencode/deepseek-v4.1-flash-free`, `{variant: max}`.

  Start a new `delegate_task` for every round, each with a new `clientRequestId`. Never send a round with `t3_thread_send`. Follow each delegate's `next`, and do not poll.
- **Outside T3:** use the harness's own subagent tools. When a seat's provider cannot be reached, it falls back as above. If DeepSeek cannot be reached either, report the empty seat.

## 4. The brief

Each seat gets the same brief, and only the brief:

```text
You are one of three independent council reviewers. You cannot see the others, and they cannot see you.
Kind: <kind>. Yardstick: <issue / plan / request>. Repo: <absolute path>.
<the packet>
<the repo profile's criteria for this kind, or "Read <absolute path to profile> section <kind>">

Rules: read only. Change no file, switch no branch, commit or push nothing, post nothing, and
start no subagents. Read code at the head SHA you were given (`git show <sha>:<path>`).
Do not suggest work outside the yardstick unless it is a defect the change introduces.

<the reply format for this kind, from below>
```

Reply formats:

- **Code, UI change, plan or other implementation detail:**
  1. Score: N/10, with one line on why.
  2. Findings, most serious first. Each has a severity (Critical, High, Medium or Low); the evidence (file:line at the head, a quote from the plan, or a screenshot's file name and what is wrong in it); what goes wrong and for whom; and the smallest fix.
  3. What would make this a 10.
  4. Satisfied: yes or no.
- **Architecture decision or feature idea:**
  1. Your pick, or the strongest version of the idea, and why.
  2. The alternatives you weighed, and what each costs.
  3. The risks, by severity, with evidence.
  4. What would change your mind.
  5. Score for the proposal as written: N/10.
  6. Satisfied: yes or no.

## 5. While the seats run

- Do not wait idle. When a result arrives, check each finding against the code at once, and decide what to fix while the other seats run.
- Do not edit files while a seat is still reviewing the same checkout. Make notes, and edit once the round is in.
- Drop a finding whose evidence does not hold up. Keep a note of it for the report.
- If the user marks a seat as non-blocking, do not wait for it. Treat a late result as feedback, and record no score for it.

## 6. Weigh the round

- A finding that two or more seats raise is strong. A finding that only one seat raises stands when you can confirm it in the code.
- List the disagreements between seats, each with the side you take and why.
- Sort each finding into one of three groups:
  - **fix now:** in scope, and confirmed;
  - **ask the user:** a product or design call, or a choice that is hard to undo;
  - **reject:** with the reason.
- The repo's rules and the yardstick win over any seat's preference.
- Fight scope creep. A finding that only widens the change goes on a follow-up list, not into this change.

## 7. Rounds

- Each full pass by the council is one round. After the fixes, a fresh review starts a new round. Give it the new head and say what changed since the last round.
- If you agree with the recommendations, make the changes, run the checks again and ask for a fresh review. Keep going until every seat answers "Satisfied: yes" and no Critical or High finding is open.
- Stop and ask the user when a round brings no new material findings but a seat is still not satisfied, or when a seat's only open asks are out of scope.

## 8. Report

When the work ends in a PR, put the results in the PR description. Place this section just before the model and harness line at the end:

```markdown
## Council review

Rounds: 2

| Seat | Model | Round 1 | Round 2 |
| --- | --- | --- | --- |
| Claude | Opus 5.5 (High) | 7/10 | 9/10 |
| Gemini | Gemini 4 Neon (High) | 7/10 | 9/10 |
| GPT | GPT-6.2 Sol (High) | 8/10 | 10/10 |

Fallbacks: none.
```

- Each row names the model and effort that actually ran. When a seat changes between rounds (for example, Neon High to Hydrogen High, or to DeepSeek), write it in that round's cell.
- When a seat gives no score, write `no score`. Never invent one.
- If the PR is open, edit its description. Do not post a comment for this.
- With no PR, put the same table in your final reply.
- Under the table, in the reply only: the findings fixed, the ones you rejected and why, the questions for the user and the follow-up list.
