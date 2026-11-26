# Review and pick

Use this reference in Phases 4 and 5 of the architect skill. It runs the arch-skills plugin over both plans, picks the winner from the evidence, and writes `final-plan.md`. Every file named here lives in the run folder.

The arch-skills skills are model-invocable. Run each one through the Skill tool as `arch-skills:<name>`. Each one reads its own repo profile and references, so don't paste them in.

## Review

### 1. One review report per plan

Run `arch-skills:architecture-review-report` once on `plan-a.md` and once on `plan-b.md`.

- Run the two reviews in two subagents started in one message, so each has a fresh context and neither sees the other plan. Pick their model as the reviewer role, as [Choosing models](#choosing-models) says.
- Give each reviewer only: the plan file, `brief.md`, and this instruction: "Invoke `arch-skills:architecture-review-report` on the plan. Treat `brief.md` as the plan's stated context. Write the full report to `<review path>` and reply with its Summary counts and Top 3 actions."
- Don't tell a reviewer which plan you lean toward, or that another plan exists.
- Save the reports as `review-a.md` and `review-b.md`.

If subagents can't invoke the Skill tool, run the two reviews yourself, one after the other, and don't reread the first plan while reviewing the second.

### 2. One decision review across both plans

Run `arch-skills:architecture-decision-review` yourself, in the main thread. Frame the decision as "Choose the architecture for `<the work>`". Give it:

- **Options:** Plan A, Plan B, and the current way or "do nothing". The skill requires the third option. Keep it.
- **Evidence:** `brief.md`, both plans, and both review reports. Name each plan's Critical and High findings in the framing, so the decision weighs them.
- **ADR:** tell it to show the ADR inline and not to write a file. Writing the ADR into the repo waits for the invoker (`SKILL.md`, Phase 6).

Let its own triage choose quick or full mode. Save its caller summary and ADR to `decision.md`.

## Pick

Apply these rules in order. Stop at the first rule that decides.

1. **Critical findings.** A plan whose review report has a Critical finding can't win while the finding stands.
   - If only one plan has a Critical finding, the other plan wins. Go to Revise.
   - If both have one, send each plan back to its planner once, with its Critical findings, and rerun step 1 of Review on the revised plans. If both still have a Critical finding, stop and report both plans and their findings to the user. Don't pick.
2. **"Do nothing" wins.** If the decision review recommends the current way or "do nothing", stop and report that with its reason. That is a valid outcome. Don't build either plan.
3. **The decision review's recommendation.** Otherwise, the plan the decision review recommends wins.
4. **Disagreement check.** If the winner has more High findings than the loser, the decision review's deciding reason must explain why those findings matter less. If it doesn't, run the decision review once more and ask that question directly. If the answer still doesn't explain it, keep the recommendation and record the disagreement under **Open questions and risks** in `final-plan.md`.

## Revise

Write `final-plan.md` from the winning plan, in the sections of [plan-template.md](plan-template.md).

1. **Fix the winner's findings.** Apply each Critical and High suggestion from the winner's review report. Apply a Medium or Low suggestion only when it is a one-line change to the plan. List every other finding under **Open questions and risks**.
2. **Take over the loser's strong elements.** Where the loser's report rates an element Positive and the winner's report has a finding on the same element, take the loser's version of that element. Take nothing the reports don't point to, and take nothing that changes the winner's direction.
3. **Carry over the decision.** Add the decision review's fitness functions to **Verification**, and its unknowns and "Revisit when" trigger to **Open questions and risks**.
4. **Re-review when a boundary moved.** If the revision changed a module, a piece of data ownership, a public interface or a dependency direction, run `arch-skills:architecture-review-report` once more on `final-plan.md` and save it as `review-final.md`. Fix any new Critical finding. If it can't be fixed, stop and report it.
5. **Write Selection.** Fill in the **Selection** section: the winner and the one reason that decided it, a table of both plans' counts (Critical, High, Medium, Low, Positive, Gaps), each finding fixed, each element taken over from the loser, and the pick rule that decided (1 to 4 above).

## Fallback: arch-skills unavailable

When the Skill tool can't load `arch-skills:*`, for example in a cloud session that installs no plugins:

1. Look for the skills as files at `plugins/arch-skills/skills/<name>/SKILL.md` in the josh-skills checkout, or in the plugin cache under `~/.claude/plugins/`. If you find them, Read each `SKILL.md` and follow it as written, in place of the Skill tool.
2. If you can't find them, compare the plans yourself. For each plan, list each red flag from [design-red-flags.md](design-red-flags.md) and each boundary crossing stronger than a name or type. Pick the plan with fewer of both. Break a tie on interface depth: the smaller public surface that hides more.
3. In `final-plan.md` and the reply, say that arch-skills did not review the pick and which of the two fallbacks you used.

## Selecting reviewers

Honor user selections and applicable repository policy. Otherwise inherit the available host default and give each planner an independent brief.
