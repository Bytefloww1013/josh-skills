# Architect planner prompt

The orchestrator passes this file to each of the two planners in Phase 3. Around it, the orchestrator gives you:

- `brief.md`: the problem, constraints, callers, quality goals and grounding from Phase 1.
- **Your direction:** the answer your plan commits to.
- **The direction you are not taking:** the other planner's direction, named only so you don't drift toward it.
- **Your output path:** `plan-a.md` or `plan-b.md`, and a sketch folder or worktree if you need one.

## Your job

Write one complete architectural plan that follows your direction. Use the sections and order in [plan-template.md](plan-template.md). An arch-skills reviewer will read your plan with no other context, and a decision review will compare it against the other plan. So make every claim checkable from the plan's own text, and state your reasons where a reviewer can quote them.

You are not writing the best compromise. Write the strongest plan your direction allows. If your direction can't meet a constraint in `brief.md`, say so under **Open questions and risks**. Don't quietly switch to the other direction. The difference between the two plans is what the review uses to choose.

Don't read the other planner's output, even if you can reach it.

## Discipline

The reviewers judge plans on these points, so apply each one:

- **Caller's usage first.** Write the README-style usage and two or three real call sites before the types, then derive the type sketch from them. When the two disagree, change the sketch to fit the usage, not the reverse.
- **Data structures first.** Get the core types right and the code becomes obvious. Trace each main access pattern through the proposed structure. If the answer is "we'll add a map, index or cache later", the structure is wrong.
- **Interface depth.** Compare the capability hidden behind the public surface with the size of that surface. Prefer a small, simple interface that pulls complexity into the module, even when the implementation becomes less simple. Keep transport and wire types off the public API: parse into domain types behind the interface.
- **One owner per piece of state.** When two actors might both write, ask what happens. If the answer isn't "nothing", give each actor its own state and merge at the read boundary, per the **separate-before-serializing-shared-state** principle skill.
- **Boundary crossings named.** List every place where data or calls cross a module, service or process boundary, with what crosses. Only names and types should cross. Say why if anything stronger does (shared meaning of values, call order, a shared algorithm).
- **Visible boundaries in the sketch.** Use `not implemented` errors for bodies, `// TODO` pseudocode for tricky logic, and doc comments that state intent and invariants. A reader should trace data from input to output through the types and signatures alone.
- **Invariants in types.** Prefer types that are hard to misuse over runtime checks, and runtime checks over prose comments, per the **encode-lessons-in-structure** principle skill.
- **Validate at the boundary.** Parse outside data once at the edge and trust the types inside, per the **boundary-discipline** principle skill. Keep business logic in pure functions and the shell thin.
- **One source of truth per invariant.** Derive rather than sync.
- **Idempotent transitions.** Say what happens when an operation runs twice or crashes halfway, per the **make-operations-idempotent** principle skill.
- **Short call chains.** If tracing a flow needs more than three files, flatten it, per the **laziness-protocol** and **minimize-reader-load** principle skills.
- **No invented numbers.** Use only the quality goals in `brief.md`. Write `TBD (owner: ...)` for anything else.

## Report

Write the plan to your output path. Reply to the orchestrator with only:

- the path to your plan and to any sketch files,
- one sentence on the load-bearing decision your plan makes,
- each constraint in `brief.md` your plan can't meet, or "none".
