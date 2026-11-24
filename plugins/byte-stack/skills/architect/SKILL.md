---
name: architect
description: "Build two structurally different architectural plans for an idea or piece of work, review both with the arch-skills plugin, and pick the better one as the plan to build. Use for /architect, 'architect this', 'design this', or non-trivial work where jumping to code would lock in the wrong shape."

---

# Architect

Design the work twice, then let an evidence-based review choose. Two planners each write one complete plan in a different direction. The arch-skills plugin reviews both and records the decision. The output is one chosen plan, revised against its review, with the losing plan and the reasons it lost kept beside it.

## Start

Open a todolist with one entry per phase:

1. Ground
2. Frame two directions
3. Build two plans
4. Review with arch-skills
5. Pick and revise
6. Hand off
7. Implement and scrap (only when the invoker asked you to build)

Make a run folder for this run's files. Use `tmp/architect/<slug>/` in the repo when git ignores `tmp/`. Otherwise use the session's scratchpad. Every file this skill names below lives in the run folder.

## Phase 1: Ground the problem

Build a real model of every system the new work touches. Naming a file isn't grounding.

1. Run the **how** skill (`../how/SKILL.md`) over each subsystem the work touches. Keep the architectural explanation it produces.
2. If the design changes ownership or layering, also explain why the existing shape is the way it is, so that reason becomes a constraint rather than a guess.
3. Read the repo's architecture doc (ARCHITECTURE.md, `docs/**/architecture.md`, AGENTS.md) and every ADR that covers the area.
4. Write `brief.md` with these sections:
   - **Problem:** what the work must do, in one paragraph.
   - **Constraints:** existing types to interoperate with, callers you can't break, invariants, ADRs in scope, rules the architecture doc says never bend.
   - **Callers:** who will use the result and how.
   - **Quality goals:** only numbers given by the user, a spec, an SLO or a measurement. Write `TBD (owner: ...)` for any other.
   - **Grounding:** the `how` explanations, or links to them.

Skip steps 1 and 2 only when the work is greenfield, with no surrounding system to integrate. Still write `brief.md`.

## Phase 2: Frame two directions

The two plans must differ in their whole shape, not in details inside one shape. This is the **exhaust-the-design-space** principle skill made concrete.

1. Name the load-bearing question the design turns on: where the state lives, which module owns the rule, what the public surface is, sync or async, one module or several.
2. Write two directions that answer it differently. Each direction is one or two sentences that commit to an answer, for example "A: one `Billing` module owns invoices and exposes three operations" and "B: invoices stay in `Orders`; a pure `pricing` library computes totals".
3. Check that they are really different. They must differ in at least one of: module map, data ownership, public interface, or dependency direction. Two flavors of one shape don't count. If you can find only one viable shape, say so in the reply with the reason, and still build a second plan along the strongest alternative, so the review has something to compare against.
4. Add both directions to `brief.md` under **Directions**.

## Phase 3: Build two plans

Start two planner subagents in one message, so they run in parallel and neither sees the other's work.

- **Brief.** Give each planner [references/planner-prompt.md](references/planner-prompt.md), `brief.md`, its own direction, and its output path: `plan-a.md` or `plan-b.md`. Pass the other direction as "the direction you are not taking", so the planner commits to its own.
- **Models.** Pick each planner's model from bphs-connect's subagent policy, `docs/agents/sub-agent-choice.md`, as the Choosing models section of [references/review-and-pick.md](references/review-and-pick.md) says. Don't name a model in this skill.
- **Isolation.** If the planners write sketch files beyond their plan, give each its own git worktree or its own subfolder of the run folder.
- **Shape.** Each plan follows [references/plan-template.md](references/plan-template.md). It must stand on its own as text, because the arch-skills reviewers read only the plan.

When both plans return:

1. Check each plan against [references/plan-template.md](references/plan-template.md). Send a plan back to the same planner, once, with the list of missing sections.
2. Screen both plans against [references/design-red-flags.md](references/design-red-flags.md). Write each red flag you find under the plan's **Red flags found** section, with the place in the plan it rests on. Don't fix the plans yourself. The review weighs the red flags.

## Phase 4: Review with arch-skills

Read [references/review-and-pick.md](references/review-and-pick.md) and follow its Review steps. In short:

1. Run `arch-skills:architecture-review-report` on each plan separately, blind to the other plan: `review-a.md` and `review-b.md`.
2. Run `arch-skills:architecture-decision-review` with both plans as the options, plus the current way or "do nothing". Give it both review reports as evidence. Save its caller summary and ADR to `decision.md`.

If the arch-skills plugin is unavailable, follow the fallback in [references/review-and-pick.md](references/review-and-pick.md), and say in the reply that the pick was not reviewed by arch-skills.

## Phase 5: Pick and revise

Follow the Pick and Revise steps in [references/review-and-pick.md](references/review-and-pick.md). They decide the winner from the review results, fix the winner's Critical and High findings, take over the loser's strong elements where the reports show them, and write `final-plan.md`.

The pick follows the review's evidence. When your own judgment disagrees with it, put that disagreement under **Open questions** in `final-plan.md`. Never override the pick silently.

## Phase 6: Hand off

Stop and present the result, unless the invoker asked you to build it (then go on to Phase 7 after this hand-off). Report:

- The chosen plan, the one reason that decided it (from `decision.md`), and the reversibility type.
- A table of both plans' review counts: Critical, High, Medium, Low, Positive, Gaps.
- What was revised in the winner and what it took over from the loser.
- The fitness functions the decision review proposed.
- The open questions and the decision's ADR, with status Proposed. A Type 1 decision needs a named person to accept it.
- The paths to `final-plan.md`, `decision.md`, both plans and both reviews.
- The first implementation step.

The ADR stays inline in `decision.md`. Write it into the repo's ADR folder only when the invoker says to, or when a calling skill's rules say where it goes.

When someone pushes back on the shape, treat it as new Phase 1 evidence. Update `brief.md`, then return to Phase 2.

## Phase 7: Implement and scrap

Run this phase only when the invoker asked you to build, or when a calling skill's go-ahead says to.

**Implement against the plan.** `final-plan.md` is the contract.

- Write the caller's usage first, then fill the sketched types and signatures with code. The scaffold can land as its own commit first, per the "scaffold first" mode of the **foundational-thinking** principle skill. Planned, scoped breakage while you fill it in is fine, per the **outcome-oriented-execution** principle skill.
- Treat a deviation from the plan as a signal to report, not friction to absorb. When a function needs a parameter the plan didn't anticipate, decide whether the plan was wrong, the requirement was missed, or the implementation is overreaching, and say which in the reply.
- For adversarial pressure before you build, run the **interrogate** skill (`../interrogate/SKILL.md`) on `final-plan.md`.

**Scrap when the architecture is wrong.** When implementation keeps producing friction the plan can't absorb, throw the plan out. Don't bolt fixes onto a wrong design, per the **redesign-from-first-principles** and **fix-root-causes** principle skills.

The signal is a pattern, not one instance. These are the tells:

- The same shape of workaround appears across unrelated code.
- Several unrelated edge cases each need a special-case branch.
- Types need escape hatches (`any`, casts, optional fields that are always set in practice) to compile.
- A lock becomes necessary where the plan said the state wasn't shared.
- Callers must know the abstraction's internal rules to use it.
- Two or more independent deviations from the plan have the same shape.

A few edge cases don't condemn an architecture. Complexity in the data is not complexity in the design.

When you scrap:

1. Run the **how** skill over what has been built, and add what it found to `brief.md` as constraints.
2. Redesign as if those constraints had been there on day one, per redesign-from-first-principles.
3. Subtract before adding, per the **subtract-before-you-add** principle skill. The new plan starts smaller than the old one.
4. Return to Phase 2. Keep the losing plan from the last round in view: it may now be the stronger direction.
