# Calibration Examples

Use these before/after pairs to calibrate compression, logic protection, Leading Words, `--deep` upgrades, and Draft Guard pivots.

---

## Example 1: Bloated, Hedged Technical Prompt (Chat Mode)

**Before (112 words):**
> Hey, so I was honestly hoping you could maybe help me write a really fast Python function that will basically handle fetching user data from our PostgreSQL database. Obviously, if the API or database gets hit too hard and returns an HTTP 429 error, it should probably just retry using exponential backoff, clearly up to maybe 5 times. Please make sure the function is very clean, definitely uses type hints, and actually logs every failed attempt to stderr. Also, it should never leak raw SQL errors to the caller, because we obviously had a security audit last quarter and the auditors were really strict about error messages.

**After (46 words — -59%):**
```markdown
Write a Python function that fetches user records from a PostgreSQL database.

## Rules
1. Use Python type hints on all parameters and return values.
2. Retry on HTTP 429 errors using exponential backoff, up to 5 attempts.
3. Log each failed attempt to `stderr`.
4. Never return raw SQL errors to the caller.
```

**Why:** Cut the audit backstory, stripped fillers and command hedges, kept `never` and exact Technical Names (`PostgreSQL`, `HTTP 429`, `exponential backoff`, `stderr`).

---

## Example 2: Logic-Trap Prompt with Source Data and Thresholds (`--in` + `--out`)

**Before (119 words):**
> Honestly, I just need you to look at the log file in `{{incident_log}}` and obviously tell me if our disk is almost full or if latency is getting too high. Please probably check whether we have enough free inodes too. Just to be clearly safe, never recommend deleting files under `/var/lib/pgdata`. Here is what the on-call engineer wrote in the ticket: "The cron job is probably causing the spike, and maybe the cache partition is nearly at 95%." Basically, summarize the root cause and list exact shell commands to verify it, and definitely do not guess if there is not enough evidence in the log.

**After (76 words — -36%):**
```markdown
Analyze `{{incident_log}}` to diagnose disk and latency issues.

## On-Call Note (Source Data)
> "The cron job is probably causing the spike, and maybe the cache partition is nearly at 95%."

## Rules
1. Check whether disk usage is almost full.
2. Check whether latency is too high.
3. Check whether free inode count is enough.
4. Never recommend deleting files under `/var/lib/pgdata`.
5. Do not guess when `{{incident_log}}` lacks enough evidence.

## Output Format
1. Root cause summary.
2. Exact shell commands to verify the findings.
```

**Why:** Removed fillers and command hedges, while preserving `{{incident_log}}`, `/var/lib/pgdata`, `never`, `almost`, `too`, `enough`, and the `probably`/`maybe`/`nearly` inside the quoted source note.

---

## Example 3: Leading Words + Draft Guard Rejection Pivot

**Before (148 words):**
> Hey, so when you build this new invoicing feature, please do not build the entire database schema first, then all the API routes, and then the whole frontend at the end, because last time we did that none of the layers connected properly and everything broke. Instead, build one tiny working path from the UI button all the way through the API and database first so we can see it working end to end. Also, try to keep your modules clean with really simple public interfaces that hide all the messy logic inside, and make sure we have clean spots where we can swap in fake payment gateways during unit tests. Finally, please do not waste time planning features three milestones ahead when we honestly do not know what customers will ask for yet; just resolve the immediate decisions right in front of us.

**Draft Angle 1 — High-Signal Leading Words (75 words — -49%):**
```markdown
Build the invoicing feature using incremental architecture rules.

## Rules
1. Start with a `tracer bullet` (`vertical slice`) from the UI button through the API to the database before expanding functionality.
2. Structure code as `deep modules` with small public interfaces that hide internal complexity.
3. Add explicit `test seams` so unit tests can swap in fake payment gateways.
4. Respect the `fog of war`: resolve only decisions on the immediate `frontier` and do not over-plan unverified future milestones.
```

**Draft Angle 2 — After Rejection (Explicit Constraints, 66 words — -55%):**
If the user rejects metaphors like `fog of war`, pivot to explicit behavioral constraints rather than making tiny wording edits:
```markdown
Build the invoicing feature incrementally.

## Rules
1. Build one end-to-end `vertical slice` from the UI button through the API to the database before adding more features.
2. Expose minimal public interfaces and encapsulate complex logic inside each module.
3. Inject the payment gateway behind an interface so unit tests can substitute a fake implementation.
4. Plan only the current milestone. Defer design decisions for unconfirmed future requirements.
```

---

## Example 4: Repo `GLOSSARY.md` Alignment + Open-Domain Leading Words

**Repo `GLOSSARY.md` terms:** `Work Ledger` (avoid: *billing log*), `Zero-Downtime Gate`.

**Before (122 words):**
> Honestly, when we move our old billing log table over to the new schema, please do not just rename columns directly and break the running servers. Instead, add the new columns first, write to both old and new columns at the same time, backfill the old data, switch reads over, and only delete the old columns after the deploy is safe. Also, please slowly replace the old legacy billing service one endpoint at a time rather than doing a big risky rewrite all at once. Finally, make sure the migration stays compatible with the previous release, and if the external tax API starts failing repeatedly, stop hammering it for 60 seconds so we do not make the outage worse.

**After (78 words — -36%):**
```markdown
Migrate the `Work Ledger` schema and replace the legacy billing service safely.

## Rules
1. Use the `expand-and-contract` pattern for all `Work Ledger` schema changes (add, dual-write, backfill, switch reads, drop old columns).
2. Enforce the `Zero-Downtime Gate` on every migration step.
3. Replace the legacy billing service incrementally using the `strangler fig` pattern, one endpoint at a time.
4. Wrap external tax API calls in a `circuit breaker` with a 60-second open cooldown after repeated failures.
```

**Why:** Reused canonical glossary terms (`Work Ledger`, `Zero-Downtime Gate`) and applied domain-native Leading Words (`expand-and-contract`, `strangler fig`, `circuit breaker`) beyond the base software examples.

---

## Example 5: Deep Mode (`--deep`) — Deeper, Not Bigger

**Command:** `/sharpen --deep Look at this summary of our slow checkout API and tell me why it is lagging. Suggest ways to make it faster and give me a checklist.`

**4-Point Depth Audit:**
1. **Expert Gap:** A top performance engineer isolates tail latency (`p95`/`p99`) by bottleneck layer (CPU, DB locks, query plans, network I/O) instead of guessing from average response times.
2. **Rawest Material:** Start from raw OpenTelemetry distributed traces, PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` plans, and raw host metrics rather than a pre-written incident summary.
3. **Specific Methods and Tools:** Apply the `RED` and `USE` methods, `pg_stat_statements`, and `k6` traffic replay.
4. **External Verification:** Re-run a reproducible `k6` load test against staging and confirm `p99` latency drops below the target SLA with zero HTTP 5xx regression.

**After (Rewritten Prompt):**
```markdown
Diagnose and resolve checkout API tail latency (`p95`/`p99`) from raw telemetry.

## Inputs (Raw Material)
* Raw OpenTelemetry distributed traces for checkout endpoints
* PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` plans and `pg_stat_statements` output
* Raw host CPU, memory, and I/O metrics during peak load

## Rules
1. Apply the `RED` and `USE` methods to isolate the primary bottleneck layer (application CPU, database locks, query plans, or network I/O).
2. Do not draw conclusions from averages or pre-written summaries alone.
3. Rank root causes by measured `p99` latency impact, citing exact trace spans or query plans.
4. Propose targeted fixes only for the top verified bottleneck.

## External Verification
1. Provide a reproducible `k6` load test script that replays peak checkout traffic in staging.
2. Require `p99` latency below the target SLA with zero HTTP 5xx regression to mark the fix complete.
```

**Why:** Same core task (fix checkout latency) with zero scope creep, upgraded from summary-based guesswork to raw telemetry, domain methods, and an independent verification oracle.
