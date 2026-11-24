---
name: principle-encode-lessons-in-structure
description: "Apply when you catch yourself writing the same instruction a second time, or notice a recurring correction. Encode the rule as a lint, metadata flag, runtime check, or script instead of more text."
---

# Encode Lessons in Structure

When the same instruction or correction comes up a second time, stop writing it again. Encode it in something that runs: a type, a lint rule, a metadata flag, a runtime check, a test, or a script in the repo's gate.

**Why:** Text works only when the next reader finds it, reads it, and remembers it. An agent that opens one file never sees the note in another. A check fires every time, for every reader, at the moment the mistake is made.

**Pattern:**
- **Notice the second time.** The trigger is repetition: the same review comment, the same correction in a session, or the same line added to a prompt or a doc again.
- **Pick the strongest place that works.** In order: a design where the mistake can't be written at all (architecture, types), then a check that fails the build (a lint rule, a compile-time check, a test), then a runtime check with a clear error, then a script in the gate.
- **Make the failure message teach.** Say what was wrong and what to do instead, so the check replaces the instruction rather than pointing at it.
- **Delete the instruction the check replaced**, per [Subtract Before You Add](../principle-subtract-before-you-add/SKILL.md). Two sources for one rule drift apart.

If the lesson needs judgment and cannot be encoded, make the instruction more prominent and add an example of the failure mode.

**Corollary:** If the fix is structural, only use the structural fix. The instruction is the symptom.

**The test:** could the same mistake land again tomorrow without anything failing? If yes, the lesson is still only text.

Distinct from [Build the Lever](../principle-build-the-lever/SKILL.md), which builds a tool for the work in front of you. This principle makes a recurring rule permanent.
