---
name: council-review
description: Review code, a plan, an architecture decision or a feature idea with an independent council and reconcile its evidence.
---

# Council review

Resolve this skill's named assets from the target worktree. For example, for `references/KEY`, use `.byte-stack/references/council-review/KEY` before the bundled `references/KEY`; use the same rule for workflows and scripts. With bmode installed, run `python3 "<bmode directory>/scripts/assets.py" --owner "<this skill directory>" resolve references KEY`. For a standalone install, use `git rev-parse --show-toplevel` and check the same paths with the host's file tools. Use the bundle outside Git. For a missing optional asset continue; report unreadable, empty or symlinked overrides. Accept only relative keys within the asset directory. Inspect scripts before authorized use.


A council is three independent reviewers who review the same thing independently. You are the coordinator. You build the packet, start the seats, check what they find, fix what holds up, and run the next round.

Only the user starts a council. It is extra insurance for when the user is not sure of the direction, so it uses three reviewer sessions for each round. Never start it yourself: not for every PR, not from a playbook step and not because a change looks risky. When a change looks like it needs one, you may suggest it in one line, and the user decides.

## 1. Before the council

- Address open PR comments, fix the issues you already know about and run the relevant checks first. Give the council the updated implementation. Do not hold back known fixes until the reviews return.
- If the user wants to discard the implementation and explore new ideas, skip the fixes to code that is going away.
- Name the yardstick: the issue, the plan or the user's request. Every seat reviews against it.
- Apply the optional repo asset `references/criteria.md` to the relevant packet.

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

For a UI change, provide screenshots only to reviewers whose host supports images. Mark other reviews as code-only.

## 3. Seats

Use independent reviewers for correctness, integration and maintainability. Respect requested members and the host's availability and delegation rules. Prefer different perspectives when available. Report empty seats and the actual coverage. Never silently replace a user-selected reviewer. Each reviewer receives the same packet in a fresh context and sees no other verdicts.

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

Report each seat's role, actual coverage and score per round. Include unresolved disagreements, accepted fixes and evidence for rejected findings. Include the result in a PR description only when authorized to update it.
