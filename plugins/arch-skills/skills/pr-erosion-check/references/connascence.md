# Connascence

Read this when a decision or a diff creates, moves or removes a dependency between two parts of the system.

## Contents
- Definition and the three properties
- The nine types, weakest to strongest
- The three rules
- How to fill the connascence table
- Severity guide
- Common cases in AI-written code

## Definition and the three properties

Two elements are connascent if a change in one requires a change in the other for the system to stay correct (Page-Jones 1992; Page-Jones 1996, *What Every Programmer Should Know About Object-Oriented Design*).

Record three properties for each pair:

| Property | Question | Values |
|---|---|---|
| Strength | How hard is it to find and fix the coupled change? | Type from the table below |
| Locality | How far apart are the elements? | same function < same module < across modules < across services/processes < across teams/orgs |
| Degree | How many elements share it? | count of call sites, consumers, or copies |

## The nine types, weakest to strongest

Static types can be seen in the source. Dynamic types appear only at run time.

| # | Type | Kind | The elements must agree on... | Example | Usual fix |
|---|---|---|---|---|---|
| 1 | Name (CoN) | static | a name | caller uses `getInvoice()` | Nothing; rename with tooling |
| 2 | Type (CoT) | static | a type | both use `Money` | Strict types; nothing else |
| 3 | Meaning / Convention (CoM) | static | what a value means | `status == 3` means "locked"; `-1` means "not found" | Enum, value object, named constant owned by one side |
| 4 | Position (CoP) | static | order of values | `createUser(name, email, isAdmin)`; tuple `(lat, lon)`; CSV column order | Named parameters, struct, record, schema |
| 5 | Algorithm (CoA) | static | one algorithm | client and server both compute the same checksum, hash, rounding or price rule | One shared function in one module; the other side calls it or receives the result |
| 6 | Execution order (CoE) | dynamic | call order | `init()` before `run()`; `open()` before `write()` | Constructor injection, builder, typestate, make invalid order unrepresentable |
| 7 | Timing (CoTm) | dynamic | when things happen | a sleep before reading a replica; timeout tuned to another service | Idempotency keys, explicit state machine, queue with ack, retries with backoff |
| 8 | Value (CoV) | dynamic | values that change together | two tables that must hold matching totals; a cache that must match its source; config duplicated in two services | Single source of truth, aggregate that guards the invariant, derive instead of store |
| 9 | Identity (CoI) | dynamic | the same instance | two modules must hold the same object or singleton; shared mutable global | Pass explicit IDs, immutable values, one owner of mutable state |

Note: some summaries list only seven types. Value and Identity are part of Page-Jones's original set and are often the most dangerous across services, so always check them.

## The three rules

1. **Degree rule.** Prefer fewer elements in any connascent group. Ten callers on a positional API is worse than two.
2. **Locality rule.** As distance grows, only weaker connascence is acceptable. Strong forms are acceptable inside one function or one module.
3. **Strength rule.** Convert stronger forms to weaker ones. Convert dynamic to static where you can.

Boundary rule used by all skills in this set: **only Name and Type may cross a module boundary.** Anything stronger across a boundary is a finding.

(The rules are from Page-Jones. Jim Weirich's talk "The Grand Unified Theory of Software Design" (2009) made them widely known. connascence.io is a good short reference.)

## How to fill the connascence table

For each option or each changed boundary:

1. List every place where information crosses: calls, imports, shared schemas, messages, files, env vars, DB tables, caches.
2. For each crossing ask: "If I change this side, what else must change?" Name the other element exactly.
3. Pick the strongest type that applies. If both CoP and CoM apply, record CoM.
4. Record locality and degree. Use counts from code search when you can (`rg -n "functionName\("`). Mark estimates with `~`.
5. Give a verdict: OK, Watch, or Fix. Fix needs a concrete change from the "Usual fix" column.

```
| # | Elements | Type | Locality | Degree | Verdict | Fix |
|---|----------|------|----------|--------|---------|-----|
| 1 | orders.api -> billing.charge(amount, currency, isRetry) | Position | across modules | 6 callers | Fix | Pass a ChargeRequest object |
| 2 | ingest worker and report parser share column order | Position + Meaning | across services | 2 | Fix | Versioned schema with named fields |
| 3 | orders and billing both store order total | Value | across modules | 2 | Fix | Billing reads total from orders, or orders publishes it |
```

## Severity guide

| Situation | Severity |
|---|---|
| Timing, Value or Identity across services or teams | Critical |
| Meaning, Position or Algorithm across modules; Execution order across modules; any dynamic type across modules | High |
| Strong form inside a module but with high degree (5+), or Meaning used widely in one module | Medium |
| Strong form with low degree inside one function or module | Low or OK |
| Change introduces a Name/Type-only boundary in place of something stronger | Positive |

High degree raises severity by one level. Static checks that enforce it (types, schema validation, contract tests) lower it by one level.

## Common cases in AI-written code

- **Magic strings shared across files** ("pending", "PAID") with no enum: CoM.
- **Copied helper** (same formatting or rounding rule pasted into two modules): CoA, and often a clone.
- **Boolean flag parameters** added to an existing function: CoP plus CoM at every call site.
- **"Just add a sleep" or bigger timeout** to fix a flaky test: CoTm.
- **Second copy of a value** (denormalized field, local cache) without an owner: CoV.
- **Module-level singletons** created for convenience: CoI.

## Change coupling (not connascence, but related)

Files that change together in history without any import between them are change-coupled (Tornhill, *Your Code as a Crime Scene*, 2015; 2nd ed. 2024). This often hides CoP, CoM or CoA that static analysis cannot see. Check git co-change when history is available (pr-erosion-check reports it for each PR; for a one-off look, `git log --format= --name-only -- <file> | sort | uniq -c | sort -rn | head`).
