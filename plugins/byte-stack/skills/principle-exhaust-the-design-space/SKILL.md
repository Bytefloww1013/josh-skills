---
name: principle-exhaust-the-design-space
description: "Apply when facing a novel UI interaction or architectural decision with no precedent in the codebase. Build 2-3 competing prototypes and compare side by side before committing."
---

# Exhaust the Design Space

When a decision has no precedent in the codebase, build two or three competing versions and compare them side by side before you commit to one.

**Why:** The first idea anchors everything after it. With one version there is nothing to compare it against, so its flaws look like the nature of the problem. Throwaway variants are cheap before you commit and expensive after.

**Pattern:**
- **Check for precedent first.** If the codebase, a decision record, or a sibling module already answers the question, follow it. This principle is for the novel case.
- **Make the variants differ in shape, not in detail:** a different owner for the state, a different interface, a different interaction model. Two flavors of one idea count as one variant.
- **Build them cheaply.** For UI, use throwaway HTML or a prototype route. For architecture, use type sketches and signatures with stub bodies; the `byte-stack:architect` skill builds two plans and reviews them. Don't put production quality into a variant.
- **Write the criteria down before you compare,** then judge every variant on the same criteria, with real data or real callers where you can.
- **Pick, then delete the losers.** Record why the winner won and what each loser showed. Take an idea from a loser only when the comparison points to it.

It also applies to product design decisions where user experience depends on feel, not logic. There, the comparison is a person using each variant.

**Stop:** Don't commit to a novel design that exists in only one version.

Distinct from [Experience First](../principle-experience-first/SKILL.md), which sets the target the comparison judges by.
