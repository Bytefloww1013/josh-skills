---
name: principle-migrate-callers-then-delete-legacy-apis
description: "Apply when introducing a new internal API while old callers still exist. Migrate callers and delete the old API in the same wave instead of preserving compatibility layers."
---

# Migrate Callers Then Delete Legacy APIs

When a new internal API replaces an old one, move every caller to the new API and delete the old one in the same change or the same planned wave. Don't keep both.

**Why:** Two ways to do one task double what readers learn and what tests cover. An agent copies whichever way it finds first, so a legacy API that stays keeps gaining callers. A compatibility shim meant to be temporary becomes permanent.

**Pattern:**
- Find every caller first, including tests, scripts, docs, and examples. Use the code index or a search, and say how you searched.
- Move all of them to the new API.
- Delete the old API, with no alias, re-export, or deprecated wrapper left behind.
- Update tests to assert the new contract, and delete tests that only protect pre-refactor implementation details
- Let the deletion itself be the guard: once the old name is gone, a caller that brings it back fails the build.

**When this applies:**
- No external users depend on backward compatibility
- The project can absorb coordinated breaking changes
- The new API is part of a simplification or refactor initiative

**When it doesn't:** external users depend on the old shape: a published package, a public HTTP API, a stored data format, or a webhook another system calls. Follow the project's versioning and deprecation rules for those.

Related: [Outcome-Oriented Execution](../principle-outcome-oriented-execution/SKILL.md) says to leave no compatibility shim behind in a phased migration.
