---
name: figure-it-out
description: "Design and run an auditable playbook for a large task that no existing playbook or single plan covers, such as a big migration or an ambitious multi-part change. Use for /figure-it-out or 'figure it out', or when bmode finds no playbook for a large task. Not for one design choice (use architect)."
---

# Figure it out

When a large task matches no playbook, design one. The deliverable before any code is the workflow itself: phases that scale rigor to the task, run the scientific method, and leave a decision log a human can audit after stepping away.

## Start

1. **Load the rules you work under.** Under bmode, read the Principles section of bmode's `SKILL.md` if you haven't this session. Its repo rules and gates win over this skill. Outside bmode, follow the repo's AGENTS.md or CLAUDE.md.
2. **Load each principle as you reach it.** This skill names principle skills by their Skill ID. Invoke each one with the Skill tool when its step comes up. Use the installed sibling’s SKILL.md when the host has no skill invocation tool. For a selective install, disclose any missing companion and proceed with the principles stated here.
3. **Open a todolist** with the phases below as items.
4. **Make the log.** Create `decision-log.md` in the run's working folder: the repo's git-ignored `tmp/` when it has one, otherwise the session scratchpad. Under bmode with a feature plan, the log lives in the plan's `## Decisions` instead.

## Phase A: Frame

Ground first, then commit. Don't start the run until you can state:

- **Done**, as a falsifiable predicate: a check that can fail (`byte-stack:principle-prove-it-works`).
- **Scope**, in numbers: rough units and effort, plus the blockers grounding surfaced. Use `byte-stack:how` to ground any subsystem you don't already understand.
- **Rigor level**, biased high. One-way doors and changes with a wide blast radius get more. Reversible, low-stakes steps get less. Rigor means gates and artifacts, not "try harder".

Present the framing and its tradeoffs before you start a long run. Reversible work proceeds without asking (`byte-stack:principle-never-block-on-the-human`), but a multi-hour run earns one checkpoint with the user.

## Phase B: Design the workflow

Break the work into small units that each land on their own. Put the riskiest unknown first. Put scaffold and verification before features (`byte-stack:principle-foundational-thinking`).

- **Harness first.** Build the verification harness before the work, and capture the baseline from the state before the change, so each check reads "old value against new value".
- **Design choices.** For a one-way-door design decision, run `byte-stack:architect`. It builds two plans and picks one with the arch-skills reviews. Skip it for mechanical work whose shape is already concrete. A second architect run over a settled design is over-engineering (`byte-stack:principle-laziness-protocol`).
- **Fan-out.** Parallelize only across seams, and give each worker its own worktree or branch (`byte-stack:principle-separate-before-serializing-shared-state`). Don't over-fan. Pick each subagent's model and reasoning level by the repo's subagent policy. Otherwise inherit the host default.
- **Write the phase list down.** That list is what the human reviews. Add it as the first entry in the decision log.

Then run the design. Add its steps to the todolist as concrete items between the Phase C and Phase D entries. Run each under the Phase C loop, and add a log row as each step lands rather than saving the log for the end.

## Phase C: Run the loop

Each unit is an experiment. State the hypothesis, make the smallest change, measure against the predicate on the real artifact, and keep the change if it advanced or revert it if it didn't. Check each unit before you start the next, rather than batching checks at the end (`byte-stack:principle-sequence-verifiable-units`).

- **Check the artifact, not a report.** When something passes too easily, suspect how you observed it before you trust the system.
- **Pair delegated work with a judge.** If a worker games the gate, reset and tighten its contract. If the gate itself is wrong, fix the gate in its own change rather than routing around it (`byte-stack:principle-attack-the-premise` when two fixes have failed the same gate).
- **Three verdicts only:** VERIFIED, NOT VERIFIED, or INCONCLUSIVE. Inconclusive is not a pass. Don't hide a negative.

## Phase D: Keep the decision log

The log, together with the diff, is what lets the human come back and trust the work. Add one row per step:

| Step | Hypothesis | Change | Measurement | Verdict | Decision and why |
| --- | --- | --- | --- | --- | --- |

- Log every decision you made without asking, with its reason, so the human can correct it.
- Log reverted steps too. A negative result is evidence.
- For ambitious work, commit the log with the change so the reviewer reads it in the PR. If the repo ignores working plans, include the relevant decisions in the review handoff.

## Phase E: Verify and hand back

Check the whole result against the Phase A predicate on the real product, not only the harness. Encode any correction that came up twice as a gate, a lint rule, a check or a script (`byte-stack:principle-encode-lessons-in-structure`).

**Reply:** the playbook you designed, the rigor level and why, the decision-log path, what is verified against the predicate, and what is still open.
