### Hillclimb

**You own the metric and the experiment's integrity.** For sustained, iterative improvement of one measurable thing against a target. A one-off fix is Bug fix (`playbooks/bug-fix.md`) or Perf issue (`playbooks/perf-issue.md`).

Not established in bphs-connect: a benchmark harness, profiler, perf tooling, in-code timing, or a CI perf job. You build the harness, and nothing in CI guards the number after the merge.

Core discipline: one change, one measurement, keep or revert. Never claim a win from reading code.

1. Name the branch before the first commit, by the rule in `docs/directives/git-and-prs.md`: `<descriptor>/<action>-issue<N>-<description>`. Use it in place of any branch name the session hands over (`AGENTS.md`). The directive has no perf descriptor. The repo's `byte-gh-issue` skill files a performance fault as a bug, so use `bug`, which maps to the `fix` type.
2. Fix one metric, the direction that counts as better, the target, and a stop rule. Use the user's numbers. Otherwise agree them with the user before the first attempt.
3. Build the harness as a `diagnosing-bugs` Phase 1 loop: one command, already run, deterministic and fast. Make it deterministic the skill's way: pin time, seed randomness, isolate the filesystem. In this repo:
   - The test kit gives an in-memory SQLite database with the real migrations.
   - `docs/verify/fixed-clock.mjs` pins the clock of the seed and the scratch server, loaded with `node --import ./docs/verify/fixed-clock.mjs` and `FIXED_NOW`. It freezes `Date.now()`, so time the harness with `performance.now()`.
   - A test inside Vitest times out at 20 seconds.
   Confirm the harness separates the slow case from an easy one, and that its run-to-run spread is smaller than the gain you are after. Make it print an error count and a count of the work done (**principle-explain-the-number**). Then freeze it. The frozen harness is the lever a reviewer reruns (**principle-build-the-lever**). Record the baseline and a green `bun run test` before any change.
4. Keep the attempt log under `tmp/`, which git ignores. One row per attempt: hypothesis, change, before, after, verdict (kept or reverted).
5. Loop, one hypothesis per attempt, one variable at a time:
   - Measure before and after with the frozen harness.
   - Run `bunx vitest run <path>` on the touched tests, then `bun run test` in full.
   - Keep the change only when the metric moves by more than the run-to-run spread and the tests stay green. Otherwise revert it in full.
   - Commit each kept change with a Conventional Commits subject. Log the row either way.
   - When two reverted attempts share one premise about where the cost is, write the premise in the attempt log and test it with the frozen harness before the next attempt (**principle-attack-the-premise**).
6. Stop at the stop rule. Do not relax it to meet it. If you are stuck, say so instead of spinning.
7. Run `docs/verify/quick-check.sh`, then **Opening a PR** (`playbooks/opening-a-pr.md`). PRs are squash-merged, so the kept commits become one commit on `main`. In the PR body, list each kept change under the template's "What and why", and give the harness command, baseline and final number under "How it was checked" (`.github/pull_request_template.md`).

**Reply:** the metric and target, baseline to final with the percent delta, attempts run (kept vs reverted), each kept change on one line, the log path, and the best idea you would try next.

Sources: .claude/skills/diagnosing-bugs/SKILL.md, server/testing/index.ts, docs/verify/fixed-clock.mjs, vitest.config.ts, package.json, AGENTS.md, .gitignore, docs/directives/git-and-prs.md, docs/verify/quick-check.sh, .claude/skills/byte-gh-issue/SKILL.md, .github/pull_request_template.md
