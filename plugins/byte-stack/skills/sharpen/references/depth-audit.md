# Depth Audit Reference (`--deep` Mode)

Use this reference when the user passes `--deep` or rejects a draft for being too shallow.

## Core Principle: Deeper, Not Bigger

A **bigger** prompt adds extra features, adjacent topics, or longer deliverables. A **deeper** prompt keeps the exact same core task but raises the standard of evidence, raw inputs, execution method, and independent verification.

| Dimension | Bigger (Avoid — Scope Creep) | Deeper (Target — Higher Rigor) |
| :--- | :--- | :--- |
| **Inputs** | Ask for five extra related documents. | Replace pre-digested summaries with the rawest primary artifact. |
| **Method** | Add unrelated subtasks and extra sections. | Name the exact domain method, standard, or tool a top practitioner uses. |
| **Judgment** | Ask for longer prose and more opinions. | Surface the omitted check, invariant, or failure mode experts inspect first. |
| **Verification** | Ask the AI to "double-check its work." | Require an external oracle (test suite, compiler, checksum, benchmark, primary record) independent of both user and AI. |

## The 4-Point Pre-Rewrite Audit

Complete all four items concisely before rewriting the prompt.

### 1. Expert Gap
Identify the single most important check, constraint, or framing that a top practitioner in the domain applies here, which the original prompt omits.
* *Example (Performance):* Measure tail latency (`p95`/`p99`) by bottleneck layer instead of inspecting averages.
* *Example (Finance):* Reconcile line-item totals against raw bank settlements before calculating margins.

### 2. Rawest Material
Replace secondary, summarized, or interpreted inputs with primary source data.
* *Instead of:* "a summary of the outage" -> *Use:* raw distributed traces, error logs, and `EXPLAIN (ANALYZE, BUFFERS)` plans.
* *Instead of:* "notes about customer feedback" -> *Use:* verbatim support transcripts and raw churn timestamps.
* *Instead of:* "a description of the code bug" -> *Use:* the failing test case, exact stack trace, and relevant source files.

### 3. Specific Methods and Tools
Name concrete, well-established techniques, protocols, CLI utilities, or analytical frameworks. Pair directly with Leading Words (`Leitwörter`) and exact Technical Names.
* *Software / Ops:* `RED` / `USE` methods, flamegraphs, `pg_stat_statements`, property-based testing, `git bisect`, `strace`.
* *Data / Finance:* cohort retention tables, three-way reconciliation, sensitivity tables, `pandas` / SQL window functions.
* *Security:* threat modeling (`STRIDE`), static analysis (`semgrep`), least-privilege IAM diffing.

### 4. External Verification
Define an objective check **outside both the user and the AI** that proves the output is correct. Never accept "looks right" or "AI self-review" as verification.
* *Code:* deterministic unit/integration tests, typechecker (`mypy`, `tsc`, `go vet`), linter, reproducible benchmark.
* *Infrastructure / Perf:* `k6` load replay against staging meeting an explicit `p99` and HTTP 5xx threshold.
* *Data / Accounting:* zero-variance reconciliation checksum against source ledger totals.
* *Documentation / Specs:* schema validation or dry-run execution by an automated parser.

## Output Placement Rule

* **In Chat / Guarded Mode:** Display the 4-Point Depth Audit directly above the rewritten prompt draft so the user can inspect and challenge every upgrade before accepting.
* **In File Modes (`--in`, `--out`):** Write **only** the clean rewritten prompt Markdown to the output file. Print the 4-Point Depth Audit in chat alongside the file confirmation.
