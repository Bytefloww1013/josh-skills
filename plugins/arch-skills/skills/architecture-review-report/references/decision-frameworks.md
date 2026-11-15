# Decision frameworks: ADR, RFC, ATAM, CBAM

Read this when choosing how heavy the decision process should be, or when writing the ADR.

## Contents
- Which framework
- ADR template (shared format)
- Rules for ADRs that agents will read
- RFC
- ATAM (escalate, do not run alone)
- CBAM (only with real inputs)

## Which framework

| Situation | Use | Who runs it |
|---|---|---|
| Any Type 1 decision, or any pattern an agent might later "clean up" | ADR | Agent drafts, human accepts |
| Type 2 decision worth remembering | Short ADR (Context, Decision, Consequences only) | Agent |
| Contract between teams: shared library, public API, event schema | RFC, then ADR | Human-led; agent drafts |
| New system or platform shift with many competing qualities | ATAM | Humans with stakeholders; agent prepares inputs |
| Choosing among large investments by return | CBAM | Humans supply utilities, weights and costs; agent computes |

Rough effort, for planning only: ADR under two hours; RFC days of async review; ATAM and CBAM days with stakeholders.

## ADR template (shared format)

Michael Nygard, "Documenting Architecture Decisions" (2011), extended with fitness functions (Ford, Parsons & Kua 2017) and a scope line so other skills can match changed files to ADRs. Keep this exact heading set; pr-erosion-check and architecture-review-report look for it.

```markdown
# ADR-NNNN: <decision as a short imperative, e.g. "Billing reads order totals through the Orders port">

- Status: Proposed | Accepted | Deprecated | Superseded by ADR-NNNN
- Date: YYYY-MM-DD
- Decision type: Type 1 | Type 2
- Deciders: <names or roles>; agent-drafted: yes/no
- Scope: <path globs this decision governs, e.g. src/billing/**, src/orders/ports/**>
- Supersedes: <ADR-NNNN or none>

## Context and forces
<facts only: constraints, quality attribute scenarios, what forces the decision now>

## Decision
<one or more invariants, each checkable. "Billing never imports from src/orders/internal/**". Not "we will try to...">

## Options considered
| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| A (chosen) | | | - |
| B | | | |
| Do nothing | | | |

## Consequences
- Positive:
- Negative / costs we accept:
- Trade-off points:

## Fitness functions
| ID | Invariant | Check | Runs in |
|---|---|---|---|
| FF-NNNN-1 | Billing does not import orders internals | import-linter contract `billing-orders-boundary` | CI |

## Revisit when
<the evidence or event that should reopen this decision>
```

MADR (Markdown Architectural Decision Records, adr.github.io/madr) is a compatible, widely used variant; its "Confirmation" section plays the same role as "Fitness functions" here. If the repo already uses MADR, keep its headings and add a Scope line.

If the repo already has ADRs in its own format, use that format and keep the same content: the path globs go in its scope field (for example YAML front matter `sources: [...]`), fitness functions in its enforcement field (for example `enforced-by: [...]`) or text, and "Revisit when" in its reopen section (for example "What would reopen it"). `adr_match.py` reads either a `Scope:` line or `sources:` front matter.

## Rules for ADRs that agents will read

- Write the Decision as invariants an agent can check. Agents treat unexplained patterns as cruft; the "Options considered" table tells them why the odd-looking code is intended.
- One decision per ADR. Never edit an Accepted ADR's decision; write a new one that supersedes it.
- Store in `docs/adr/NNNN-kebab-title.md`. Link the ADR from the code it governs when the pattern looks unusual (one comment line: `// See ADR-0012`).
- Status "Accepted" for a Type 1 decision requires a named human.
- When the user rejects an option for a lasting reason, offer to record it as an ADR, so later reviews and agents do not propose it again.

## RFC

Use for decisions that change what other teams depend on. Contents: problem, proposal, alternatives, migration plan, open questions, review deadline. The accepted RFC becomes an ADR.

## ATAM (escalate, do not run alone)

Architecture Tradeoff Analysis Method (Kazman, Klein & Clements, SEI, 2000). Stakeholders build a utility tree of quality attribute scenarios, the architecture is analysed for risks, sensitivity points and trade-off points. An agent cannot do this alone because it needs stakeholder priorities. What the agent can do: draft the scenario list and the candidate risks, and flag "ATAM recommended" in the output.

## CBAM (only with real inputs)

Cost Benefit Analysis Method (Kazman, Asundi & Klein, ICSE 2001), built on ATAM outputs.

For each strategy i and scenario j, with stakeholder weights W_j (sum to 100) and utilities U in [0, 100]:

```
EU_i  = sum_j  W_j * (U_projected(i, j) - U_current(j))
ROI_i = EU_i / Cost_i
```

Run it only if a human has supplied the weights, utilities and costs. Never invent them. If they are missing, list exactly which inputs you need and stop.
