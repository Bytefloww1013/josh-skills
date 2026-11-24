---
name: principle-laziness-protocol
description: "Apply when refactoring, evaluating diff size, or tempted to add abstractions, layers, or signal threading. Bias toward deletion and the smallest change that solves the problem."
---

# Laziness Protocol

Do the least work that fully solves the problem. Bias toward deletion and the smallest change.

**Why:** Every added line, layer, and option is something the next reader must understand and the next maintainer must keep working. Code you didn't write has no bugs and costs nothing to read.

**Pattern:**
- **Minimize the diff.** Make the smallest change that solves the problem. Fewer lines beat "elegant" boilerplate.
- **Consolidate decisions.** Do not repeat the same choice in several places. Put it behind one source of truth and pass the result as a simple flag.
- **Delete before you write.** If removing code solves the problem, remove it.
- **Reuse what exists.** Look for the helper, type, or pattern the codebase already has before you write a new one.
- **Add no layer you can't justify today:** no wrapper with one caller, no adapter with one implementation, no option nobody sets, no flag threaded through modules that don't use it.
- **Stop at done.** Don't polish, generalize, or fix things "while I'm here" past the requirement. Note the follow-up instead.

Lazy is not careless. The verification and the companion changes the project requires in the same change (tests, docs, generated files) are part of the smallest *complete* change.

**The test:** can you remove any line of the diff and still solve the problem? If yes, remove it.

Related: [Subtract Before You Add](../principle-subtract-before-you-add/SKILL.md) sequences removal ahead of construction, and [Minimize Reader Load](../principle-minimize-reader-load/SKILL.md) judges whether a layer earns its place.
