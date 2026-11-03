### Perf issue

**You own the numbers.** Every fix ties to a before and an after measurement from the same command. Do not read source in place of measuring.

Not established in bphs-connect: benchmark, profiler, load-test or Lighthouse tooling, in-code timing calls, or a CI perf job. You build the measurement.

1. Name the branch by `docs/directives/git-and-prs.md`. The directive has no perf descriptor. The repo's `byte-gh-issue` skill files a performance fault as a bug, so use `bug`, which maps to the `fix` type.
2. Run the repo's `diagnosing-bugs` skill on its perf branch. Logs are usually the wrong tool. Establish a baseline measurement (timing harness, `performance.now()`, profiler, query plan), then bisect. Measure first, fix second.
3. Build the harness as the skill's Phase 1 loop: one command, already run, that shows the user's slowdown. Options in this repo:
   - A Vitest test against the test kit's in-memory database with the real migrations. A test times out at 20 seconds (`vitest.config.ts`).
   - A script against the seeded scratch server, `docs/verify/scratch-server.sh start`.
   - Put scratch output under `tmp/`, which git ignores.
   Data comes from the seed or from rows the harness inserts. Never use a real backup or a copy of the live database (`docs/directives/production-safety.md`).
   Record the baseline number and the exact command before any change. First write down the result that would change the decision. Run each side at least 5 times, alternating, and record the median and range. Vet the harness per **principle-explain-the-number**.
4. If the slowdown appeared between two known states, bisect with the skill's bisection harness and `git bisect run`.
5. Change one variable at a time. Measure after each change with the same command. A new index goes in its module's `server/schema.ts`, then `bun run db:generate --name <what>` (`docs/references/modules.md`).
   Precedent: commit `6998134` (migration 0026) gives its numbers in the message ("on 25k condition rows the Employees list goes from 2128 ms to 1.9 ms") and pins the fix in `modules/assets/server/conditions-index.test.ts`, which asserts `explain query plan` names the index and has no `SCAN`. Commit `8bdac41` made the Tasks line read only the columns it needs, through a new index `ix_tasks_assigner` (migration 0028), pinned the same way in `modules/tasks/server/summary.test.ts`. Write a regression test only at a seam that reproduces the real pattern; if none exists, note that as a finding (diagnosing-bugs Phase 5). Pin the index with the query the code runs, as the `OPEN_SQL` case in `conditions-index.test.ts` does, not with a copy of it (**principle-test-behavior-not-implementation**).
6. Remove the harness or leave it under `tmp/`. Run `bun run format`, then `bun run lint`, which must exit 0 with no warnings, then `docs/verify/quick-check.sh`. Its quick checks include `migrations:check`, `schema-drift.sh` and `migrations:fks`, which a new index migration must pass.
7. State the confirmed cause in the commit or PR message, with the baseline and post-fix numbers, the run count and range, the limiter (such as a `SCAN` the index removes), the row count, the Node version and the command.
8. Run **Opening a PR** (`playbooks/opening-a-pr.md`).

For sustained improvement against a metric rather than a one-off fix, use Hillclimb (`playbooks/hillclimb.md`).

**Reply:** the command, the baseline and post-fix numbers with run count and range, the delta, the limiter, and any artifact path.

Sources: .claude/skills/diagnosing-bugs/SKILL.md, .claude/skills/byte-gh-issue/SKILL.md, docs/directives/git-and-prs.md, docs/directives/production-safety.md, docs/references/modules.md, AGENTS.md, vitest.config.ts, server/testing/index.ts, docs/verify/scratch-server.sh, .gitignore, docs/verify/quick-check.sh, docs/verify/gate-checks.txt, modules/assets/server/conditions-index.test.ts, modules/tasks/server/summary.test.ts
