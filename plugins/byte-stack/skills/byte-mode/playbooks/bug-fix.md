### Bug fix

**You own the fix and its evidence.** Every shipped line traces to a run that went red, then green. A change that "might help" is a hypothesis, not a fix. It does not ship.

1. Name the branch before the first commit, by the rule in `docs/directives/git-and-prs.md`: `bug/<action>-issue<N>-<description>`: an action from the directive's list, the issue number, two or three lower-case words. The `bug` descriptor maps to the `fix` type. Use it in place of any branch name the session hands over (`AGENTS.md`). `bun run names:check` fails any other name.
2. Run the repo's `diagnosing-bugs` skill. It owns the phases. Skip one only with a stated reason. Redact every secret first: write `<REDACTED>` in its place.
3. Build the feedback loop (Phase 1). It is one command you have already run, that asserts the user's exact symptom and can go red on this bug. No red-capable command, no hypotheses: if you cannot build one, stop, say so, list what you tried, and ask the user. Never build the loop on a real backup or a copy of the live database (`docs/directives/production-safety.md`). Loops this repo supports:
   - A Vitest test at the seam that reaches the bug, run with `bunx vitest run <path>`. Server tests use the test kit: `setup()` in `server/testing/index.ts` opens an in-memory SQLite database and runs the real migrations.
   - A script against the seeded scratch server: `docs/verify/scratch-server.sh start|stop`, on port 3388, never the real DATA_DIR.
   - A browser check: `node docs/verify/browser.mjs <address>` fails on a console error or an error page.
   - The skill's `scripts/hitl-loop.template.sh`, only when a human must act. It is the last resort.
4. Reproduce and minimise until every remaining element is load-bearing. Then write 3 to 5 ranked, falsifiable hypotheses. Show the list to the user before testing, without blocking on an answer (**principle-never-block-on-the-human**).
5. Instrument one variable at a time. Tag every temporary log with a unique prefix, such as `[DEBUG-a4f2]`. The server has no logger: `console` is its log. Elsewhere `no-console` is an error in `.oxlintrc.json` (`scripts/` and `web/src/lib/submit.ts` are exempt), so a debug log there fails lint until removed. The test kit builds the app with `quiet: true`, so `hono/logger` request lines do not print in tests.
6. Write the regression test before the fix, and only at a correct seam. If no correct seam exists, report that as a finding. Write it in Vitest (`vi.fn`, `vi.spyOn`). Mock only at system boundaries. For the database, use the test kit's in-memory database. Drive the test through the module's API with the test kit (`t.call`), assert what the caller sees, and take the expected value from the bug report, not from a run of the code (**principle-test-behavior-not-implementation**). Follow the vendored `tdd` skill for the red-green loop and its anti-patterns (`.claude/skills/tdd` in the repo, also bundled beside this skill at `../../tdd/SKILL.md`). It also has you write down the seams under test and confirm them with the user before writing any test.
   Precedent: `fix(maintenance): forget a deleted request's notifications (#69)` added its regression test to `modules/maintenance/server/maintenance.test.ts`, and a cross-module guard, `server/tests/notification-sources.test.ts`.
7. Watch the test fail. Apply the smallest fix the evidence justifies, at the first place the code went wrong, not where the symptom showed. A guard, retry, catch or clamp is the fix only when the state it handles is legitimate (**principle-laziness-protocol**, **principle-fix-root-causes**). Fix each other instance of the fault the issue covers, and list the rest in `tmp/pr-body.md` for the user. Watch it pass. Re-run the original, un-minimised Phase 1 loop.
   - If two fixes that share one premise leave the test red, stop fixing. Write the premise down and test it with the loop before a third fix. If the evidence contradicts it, return to step 4 and rank new hypotheses (**principle-attack-the-premise**). The test and the loop stay as they are.
8. Clean up. Grep `[DEBUG-` and remove every hit. Delete throwaway harnesses. Run `bun run format`, then `bun run lint`, which must exit 0 with no warnings, then `docs/verify/quick-check.sh`.
9. State the hypothesis that proved correct in the commit or PR message. Commit subjects follow Conventional Commits.
10. Run **Opening a PR** (`playbooks/opening-a-pr.md`).

**Reply:** what was broken, the root cause, the fix, the red-capable command, and its failing-then-passing output verbatim, redacted.

#### Drift in the repo skills

- `diagnosing-bugs` and `tdd` say to read `GLOSSARY.md` if it exists. The repo has none. The glossary is `docs/references/project-glossary.md`.
- The `tdd` skill's `tests.md` example uses `jest.mock`. The repo has no Jest. Tests run on Vitest.

Sources: .claude/skills/diagnosing-bugs/SKILL.md, .claude/skills/diagnosing-bugs/scripts/hitl-loop.template.sh, .claude/skills/tdd/SKILL.md, .claude/skills/tdd/tests.md, .claude/skills/tdd/mocking.md, docs/directives/git-and-prs.md, docs/directives/production-safety.md, AGENTS.md, CLAUDE.md, package.json, server/testing/index.ts, server/app.ts, .oxlintrc.json, docs/verify/scratch-server.sh, docs/verify/browser.mjs, docs/verify/quick-check.sh, modules/maintenance/server/maintenance.test.ts, server/tests/notification-sources.test.ts, web/src/lib/submit.test.ts, server/tests/api.test.ts, docs/references/project-glossary.md
