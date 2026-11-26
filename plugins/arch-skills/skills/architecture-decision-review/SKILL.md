---
name: architecture-decision-review
description: Reviews a design choice before it is built and returns an ADR with a reversibility call, a connascence table and fitness functions. Use when choosing between design options, or before a plan adds, splits or moves a module, dependency, schema or public API.
---

# Architecture Decision Review

Turn a design choice into a recorded, checkable decision. The effort matches how hard the choice is to undo: most choices take the quick path.

## The core rule

A decision that changes a boundary is not done until it has three things:
1. a reversibility call (Type 1 or Type 2) with the evidence for it,
2. a connascence row for every place where information crosses the boundary,
3. at least one fitness function, or a stated reason why none is possible.

Why: these three are what the next reviewer and the next agent need. Without them, a sound decision looks like cruft and gets "cleaned up", or a weak one spreads before anyone sees it.

## Step 0. Repo first

If the repo has `app.modules.ts` and `docs/verify/gate-checks.txt`, read `references/project-bphs-connect.md` before triage. It names the module tiers, the rules that never bend, the checks the repo already runs and its ADR format. In any repo, read its own architecture doc (ARCHITECTURE.md, `docs/**/architecture.md`, AGENTS.md) before you propose a boundary: the decision must fit the rules it states or say which rule it changes.

## Step 1. Triage (always; two minutes)

Answer four questions. They choose the mode and which reference files to read. Do not read every reference file.

**Q1. Does it touch a boundary?** A boundary is any place where code or data crosses between modules, packages, services, processes or teams: imports, calls, schemas, events, files, shared tables, caches, env vars. If yes, the connascence lens is required (read `references/connascence.md`).

**Q2. Type 1 or Type 2?**

| Type 1 (one-way door) if any is true | Type 2 (two-way door) if all are true |
|---|---|
| Changes the shape or ownership of stored data | No stored data changes, or only additive |
| Changes a public API, event or file format others use | All callers are in this repo |
| Undo would take many modules, services or teams | Undo is one PR in one module |
| Changes tenancy, auth or a trust boundary | Sits, or can sit, behind a port |

Unsure after the table: read `references/tradeoffs-reversibility.md` and run its four-question reversibility test. Still unsure: treat it as Type 1.

**Q3. What kind of decision is it?** Read only the rows that match.

| The decision is about... | Read |
|---|---|
| A new or changed dependency; splitting or merging modules | `references/coupling-metrics.md`; run `scripts/coupling_metrics.py` (TypeScript, JavaScript, Python; `--module` names the modules) |
| A data model, schema, API, event or file format | `references/contracts-evolution.md` |
| Competing qualities (speed vs consistency, cost vs resilience), or choosing a technology or vendor | `references/tradeoffs-reversibility.md` |
| A migration, rewrite, feature layout or rollout | `references/delivery-patterns.md` |
| Which process to use (ADR, RFC, ATAM, CBAM), or writing the ADR | `references/decision-frameworks.md` (always in full mode) |
| Turning the decision into checks | `references/fitness-functions.md` (always in full mode) |
| Rating the risks you found | `references/severity.md` |

Most decisions need two or three files.

**Q4. Is there an ADR already?** Search before deciding: `rg -il "<module or concept>" docs/adr docs/decisions doc/adr 2>/dev/null`. If one is in scope, the new decision follows it or explicitly supersedes it. Never contradict an ADR silently.

**Mode:** Type 2 goes to quick mode. Type 1 goes to full mode. A Type 2 choice whose connascence row comes out stronger than Name or Type across a boundary moves up to full mode.

## Step 2a. Quick mode (Type 2)

1. Frame it in one sentence: "Choose X for Y because Z."
2. Name the current way (or "do nothing") and one alternative.
3. If Q1 was yes, write 1 to 3 connascence rows for the crossings.
4. Pick one. Say what would make you revisit it.
5. If the choice will look odd to a later reader, write a short ADR (Context, Decision, Consequences, Scope). Otherwise the decision note below is enough.

```
DECISION NOTE: <title>
Choice: <option> over <alternative>; Type 2 because <evidence>
Crossings: <connascence rows, or "none">
Revisit when: <trigger>
```

## Step 2b. Full mode (Type 1)

Copy this checklist into your working notes and tick it off. Go back a step when a later step shows a gap.

```
- [ ] 1 Context: read AGENTS.md / CLAUDE.md, ARCHITECTURE.md, ADRs in scope, public entries of touched modules
- [ ] 2 Frame: "We must decide X because Y. The last responsible moment is Z."
- [ ] 3 Options: 2 to 4, one is the current way or "do nothing"
- [ ] 4 Quality attribute scenarios: 1 to 3, six parts each
- [ ] 5 Information hiding: what change does each module hide?
- [ ] 6 Connascence table for each option
- [ ] 7 Dependency direction: arrows inward, no new cycles, stable direction
- [ ] 8 Trade-off points: at most 3 per option
- [ ] 9 Reversibility: if evidence is missing, port + cheapest choice + evidence needed
- [ ] 10 Recommendation with the one reason that decides it
- [ ] 11 ADR (status Proposed) with fitness functions
- [ ] 12 Self-check
```

Notes on the steps that need judgement:

- **1 Context.** Read public interfaces first (`index.ts`, `__init__.py`, package API, OpenAPI). Read internals only to answer a specific question.
- **4 Scenarios.** Numbers come only from the user, the spec, an SLO or a measurement. Otherwise write `TBD (owner: ...)` and add it to open questions. See `references/tradeoffs-reversibility.md`.
- **5 Information hiding (Parnas 1972).** Each module should hide one decision that is likely to change (a vendor, a format, a rule). A split by processing step (parse, validate, save) is a red flag, because one change in data shape cuts through every step.
- **6 Connascence.** Use the table format in `references/connascence.md`. Check all nine types, including Value and Identity. Only Name and Type may cross a module boundary; anything stronger needs a fix in the table or a reason in the ADR.
- **7 Direction.** Run `python3 scripts/coupling_metrics.py --root <src> [--module ...] --json` before and after (the after state can be a sketch). Run with `--help` first. Domain code importing a framework, database, HTTP client or LLM SDK is Critical unless an ADR allows it.
- **9 Reversibility.** When a Type 1 choice lacks evidence, recommend a thin port, the cheapest choice behind it, and the exact evidence and date that would settle it.
- **11 Process.** If the decision needs stakeholder priorities (ATAM) or cost-benefit inputs (CBAM), do not invent them. Say "ATAM recommended" or list the CBAM inputs needed, and stop that part.

## Step 3. Output contract

Return two things, in this order. Other skills and agents parse the first one, so keep the field names.

**A. Caller summary**

```
DECISION REVIEW: <title>
Mode: quick | full        Type: 1 | 2        Sign-off: needed from <role> | not needed
Recommendation: <option>. <one sentence: the reason that decides it>
Top risks:
  1. <severity> <connascence type or principle>, <locality>, <degree>: <one line>
  2. ...
Fitness functions: <FF-ID: tool + rule> | none: <reason>
Unknowns: <what is assumed or TBD, with owner>
Revisit when: <trigger>
ADR: <path written> | inline below
```

**B. ADR** in the shared template from `references/decision-frameworks.md` (Status, Date, Decision type, Deciders, Scope, Context, Decision as invariants, Options considered, Consequences, Fitness functions, Revisit when). If the repo already has ADRs in another format, use the repo's format and carry the same content: path globs go in its scope or `sources:` field, fitness functions in its enforcement field or text, and "Revisit when" in its reopen section.

- If you are already changing this repo for the user and it has an ADR folder, write the file there with the next number. Otherwise show the ADR inline and offer to save it (suggest `docs/adr/` if there is no folder).
- Status is always `Proposed`. A Type 1 ADR becomes `Accepted` only when a named human accepts it.
- The `Scope:` line (or the repo's `sources:` front matter) lists path globs. pr-erosion-check uses it to find which ADRs govern a diff, so keep it accurate.

## Red flags: stop and correct yourself

| If you think... | Do this instead |
|---|---|
| "Only one option makes sense." | Add the current way or "do nothing" as an option. If it truly loses, the table shows why in one row. |
| "I'll add an interface so it is extensible." | Add a port only in front of something volatile (vendor, I/O, framework). Otherwise wait for a second real case (rule of three). |
| "The load is probably around..." | Do not estimate. Write TBD with an owner. |
| "This old pattern looks like cruft." | Search the ADRs and git log for why it exists before you replace it. If you find no reason, ask. |
| "It's Type 2, we can change it later." | Only if it sits behind a port. A choice that spreads to many call sites becomes Type 1. |
| "A connascence table is overkill here." | For a boundary crossing it is the core output. Two rows is fine. |
| "The user asked me to decide, so I'll mark it Accepted." | Recommend firmly; leave the ADR Proposed for a Type 1 decision. |
| "Let me read every reference file to be thorough." | Read only what triage selected. More text makes the review worse, not better. |

## Gotchas

- A request phrased as a quick question ("Redis or Postgres for this queue?") still gets quick mode, not a full ADR. Offer full mode in one line if triage says Type 1.
- When the decision is being made inside another agent's plan, return the caller summary first and keep it short; the caller may be mid-task.
- The metrics script cannot see dependency-injection wiring, computed dynamic imports, or languages other than TypeScript, JavaScript and Python. Say "qualitative" and reason from the imports you read.
- When the user rejects an option for a lasting reason ("we will never run our own Kafka"), offer to record that as an ADR so the next review does not suggest it again.
- Change coupling (files that always change together with no import between them) hides Position, Meaning and Algorithm connascence. If git history is available and the decision touches such files, check `git log --format= --name-only -- <file> | sort | uniq -c | sort -rn | head`.

## Self-check before you return

- Every risk names its evidence: a file, a line, a quote from the user or spec.
- No invented numbers, costs, utilities or load figures.
- Every boundary crossing has a connascence row; every row stronger than Type across a boundary has a fix or an ADR reason.
- At least one fitness function names a real tool and rule, or the summary says why none is possible.
- Status is Proposed; Sign-off says who, for Type 1.
- The caller summary is first and fits on one screen.
