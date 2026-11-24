# Plan template

Each planner writes its plan in these sections, in this order. `final-plan.md` uses the same sections plus **Selection**. Use sentence-case headings and no boilerplate. Replace each italic note with real content.

The plan must stand on its own. An arch-skills reviewer reads it with no other context and quotes it as evidence, so state each decision and its reason in words a reviewer can quote.

## Direction

*One or two sentences: the direction this plan commits to, copied from `brief.md`, and the load-bearing decision that follows from it.*

## Problem

*One paragraph. What the work must do, and what about the existing system or constraints makes the shape non-obvious. Name the constraints from `brief.md` the design must honor: existing types to interoperate with, callers you can't break, invariants that cross the boundary, ADRs in scope.*

## Usage (caller's view)

*Write this first, before the shape. Show the README or quickstart the consumer reads, plus two or three realistic call sites in their own code: what they import, what they call, what comes back. The sketch in Shape is derived from this, and the two must agree. When they disagree, change the sketch to fit the usage. The caller's experience is the spec.*

## Shape

*The architecture. Data structures first, then how data flows through the signatures.*

- *Module map: each module, the one decision it hides, and what it owns.*
- *Data and ownership: each stored or shared piece of state and its single owner.*
- *Type sketch and signatures: one code block for small work, or a module map plus type definitions for larger work. Bodies are `not implemented`; tricky logic is `// TODO` pseudocode.*
- *Invariants: which are encoded in types, where validation lives, and what the system deliberately does not do.*
- *Interface depth: what complexity the public surface hides, what stays exposed to callers, and why the interface is no larger than needed.*

*Cite the principle behind each load-bearing decision (for example, "per boundary-discipline"). Don't restate it.*

## Boundary crossings

*One row per place where data or calls cross a module, package, service or process boundary.*

| From | To | What crosses | Why it is safe, or what it couples |
| --- | --- | --- | --- |

## Dependency direction

*Which modules import which. Name any new dependency, any dependency on a framework, database, HTTP client or SDK from domain code, and confirm there is no new cycle.*

## Delivery

*How the change lands: phases or slices, any migration of stored data, and how existing callers move to the new shape. Say which steps are hard to undo.*

## Verification

*How the work will be proved: the tests by behavior, and at least one check that keeps the design from eroding later (a lint rule, an import rule, a type, a script). Say "none possible" with the reason if there is none.*

## Tradeoffs accepted

*One bullet per tradeoff, in the form "we accept X in exchange for Y". Name anything a future reader might mistake for an oversight, such as something that looks like premature optimization or premature simplification.*

## Alternatives considered

*At least one concrete alternative shape inside this direction, with one line on why it lost, judged on interface depth: what it exposes to callers and what it hides. Don't list the other planner's direction here.*

## Open questions and risks

*Things the human needs to decide, and risks to flag before implementation. Write them as questions, so the human's answer is the resolution. Include each constraint in `brief.md` this plan can't meet.*

## Red flags found

*Filled in by the orchestrator in Phase 3 from [design-red-flags.md](design-red-flags.md): each red flag, with the place in this plan it rests on. Planners leave this section empty.*

## Selection

*Only in `final-plan.md`, filled in by the orchestrator in Phase 5 as [review-and-pick.md](review-and-pick.md) says: which plan won and the one reason that decided it, both plans' review counts, each finding fixed in the revision, each element taken over from the losing plan, and the review's fitness functions.*

## Next implementation step

*The first thing to build against this plan, in one sentence.*
