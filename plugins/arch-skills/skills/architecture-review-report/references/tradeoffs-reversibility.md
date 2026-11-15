# Trade-offs and reversibility

Read this for any decision that is not a quick Type 2 call: when quality attributes compete, or when you must decide how hard the choice is to undo.

## Contents
- Type 1 and Type 2 decisions
- Reversibility test
- Last responsible moment and options
- Quality attribute scenarios
- Sensitivity and trade-off points

## Type 1 and Type 2 decisions

Bezos (2015 Amazon shareholder letter): Type 1 decisions are one-way doors, consequential and hard to reverse; Type 2 are two-way doors and should be made fast by small groups.

Classify with evidence, not feel:

| Signal | Points to Type 1 | Points to Type 2 |
|---|---|---|
| Data | Changes how persistent data is shaped, owned or partitioned | No stored data changes, or change is additive |
| Contracts | Public API, event schema or file format other teams or clients use | Internal interface with all callers in this repo |
| Blast radius | Many modules, services or teams must change to undo it | One module; undo is one PR |
| Isolation | Not behind a port or interface | Behind a port; swap is local |
| Cost to exit | Migration, data backfill, contract renegotiation, vendor lock-in | Delete and replace |
| Security / tenancy | Changes isolation, auth model or trust boundary | Does not |

Typical Type 1: primary data model, tenant isolation model, sync vs async between services, public API shape, choice of system of record, identity/auth model.
Typical Type 2: parser library behind a port, internal cache backend, internal module layout, logging library.

A Type 2 choice made without a port can become Type 1 over time. If it spreads (degree grows), wrap it now.

## Reversibility test

Answer these four in one line each:
1. What would we have to change to undo this in six months?
2. Who outside this repo would notice?
3. Is any data written in a shape we could not read back after undoing?
4. Can we put it behind an interface today for less than a day of work?

Two or more answers that point to wide or permanent effects means Type 1.

## Last responsible moment and options

Poppendieck & Poppendieck (2003, *Lean Software Development*): delay a commitment until the cost of not deciding is greater than the cost of deciding. This is not "delay forever".

When a Type 1 choice lacks evidence:
- Put a thin port in front of the uncertain part.
- Make the cheapest choice behind it.
- Name the evidence that would settle it (a load test, a customer contract, a cost figure) and the date or trigger by which you must decide.

## Quality attribute scenarios

Bass, Clements & Kazman (2021, *Software Architecture in Practice*, 4th ed.). Replace words like "fast", "scalable" or "extensible" with six-part scenarios:

| Part | Example |
|---|---|
| Source | External webhook provider |
| Stimulus | 500 events arrive in one second |
| Artifact | Ingestion pipeline |
| Environment | Normal operation, peak hour |
| Response | Each event is persisted and acknowledged |
| Response measure | p99 acknowledge time below 150 ms; zero lost events |

Modifiability example: Source: developer or agent; Stimulus: add a new compliance rule; Artifact: policy engine; Environment: development time; Response: rule added in one new module; Measure: no edits to existing modules, one PR under 200 changed lines.

Only write numbers that come from the user, the spec, an SLO or measurement. If no number is known, write `TBD (owner: ...)` and record it as an open question.

## Sensitivity and trade-off points

- **Sensitivity point:** a parameter that strongly affects one quality attribute (pool size affects throughput).
- **Trade-off point:** a parameter that affects two or more attributes in opposite directions (synchronous replication improves durability and worsens write latency).

For each option, name at most three trade-off points. Each one is a candidate fitness function or monitoring alert.
