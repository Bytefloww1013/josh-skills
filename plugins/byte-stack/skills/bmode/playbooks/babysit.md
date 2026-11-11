### Babysit

**Drive one PR on `main` to green, then stop. Merging waits for the user's word.**

Babysitting starts when the user asks for it, not when a PR opens. A request to merge, land or ship is `playbooks/shipping.md`, which begins where this playbook ends.

1. **Read the state.** Run `gh pr checks <pr>` for the checks, `gh run list --branch <branch> --limit 3` for the recent runs, and `gh run watch <id> --exit-status` to wait on one run.
2. **Know the expected checks.** Two workflows run on every PR to `main`:
   - `PR checks` (`.github/workflows/pr-checks.yml`), job `Stale docs, branch and title`: `bun run docs:stale`, then `bun run names:check`. It runs on open, push, reopen and each new title or body. A new run cancels the one in progress, so a `CANCELLED` run before a `SUCCESS` is normal. `Start CI on a retargeted PR` is skipped unless the PR's base changes to `main`.
   - `CI` (`.github/workflows/super-linter.yml`): `Fast checks`, then `Typecheck, test, build` and `Super-Linter`. `bun run ci:scope` picks the scope from the paths. Scope `text` (Markdown alone) skips the last two jobs, and `Fast checks` then also runs `bun run test scripts/`. Scope `tooling` skips `Build`, `Install Chrome` and `Route smoke`. A skipped job reports Success (`gh pr checks` prints `skipping`). A push cancels the CI run in progress for that PR. A new title or body does not rerun CI.
   - `New module proof` (jobs `New module proof (feature)` and `New module proof (foundation)`) runs on a PR only when it touches that workflow's paths: `scripts/templates/**`, `scripts/new-module.ts`, `docs/verify/new-module-proof.sh` or the workflow file.
3. **Resolve conflicts first.** `git fetch origin`, `git rebase origin/main`, rerun the tests, then `git push --force-with-lease -u origin <branch>`. Push only this PR's branch.
4. **Fix a failing check at its local command.** `docs/verify/gate-checks.txt` names each check's CI job and its local command. Run that command, fix in a new commit with a Conventional Commits subject, rerun `docs/verify/quick-check.sh`, then push. If two fix commits that share one premise fail the same check, stop pushing. Write the premise down and test it at the check's local command before the next commit (**principle-attack-the-premise**). `quick-check.sh` runs only the checks marked `quick`. The ones marked `ci` run in CI or by hand, and Super-Linter has no line.
   - `Branch and title`: the branch name or the title breaks `docs/directives/git-and-prs.md`, and the title's type must be the one the branch's descriptor maps to. Fix the title on the PR. A new title reruns `PR checks` alone. Not established in bphs-connect: renaming a PR's branch.
   - `Stale docs`: edit the stale doc, or add a `docs-unaffected: <doc> - <reason>` line to the PR body. Add the same line to `tmp/pr-body.md`: CI reads the PR body, but a local `docs:stale` reads that file. A new body reruns `PR checks` alone.
   - `Fast checks`: for `format:check`, run `bun run format`. For `modules:gen --check`, run `bun run modules:gen` and commit the registries. For any other step (migrations, `docs:check`, `docs:terms`, `tables:refs` and the rest), run its `checks` line in `gate-checks.txt`.
   - `Typecheck, test, build`: `bun run lint`, `bun run typecheck`, `bun run test`, `bun run build`, then the route smoke, `node docs/verify/routes-smoke.mjs` (CI only).
   - `Super-Linter`: it runs only in CI (gitleaks, hadolint, shellcheck, actionlint, zizmor, yaml). On a PR it lints only the changed files. TypeScript is left to the other jobs. Its result also arrives as a PR comment (`../references/triage.md`), and `gh pr checks` adds one `--> Linted: <LINTER>` line per linter.
   - `New module proof`: a stale template in `scripts/templates/module/` fails it. Run `docs/verify/new-module-proof.sh`, with `TIER=foundation` for the foundation job.
5. **Retries.** Not established in bphs-connect: a flake or retry rule. `gh workflow run CI --ref <branch>` reruns CI by hand, but that run tests the branch, not the PR merged into `main`.
6. **Triage comments** per `../references/triage.md`. No PR in the repo has a review.
7. **Stop at green.** Merge-ready means every expected check passes on the PR's current head. The repo has no CODEOWNERS file, and GitHub refuses to read branch protection and rulesets for `main` (403, "Upgrade to GitHub Pro or make this repository public"), so no required reviewer or check is known. Report and stop. A babysit never merges. Only the user's word does, through `playbooks/shipping.md`.

Not established in bphs-connect: stacked PRs, a merge queue, or an automated review bot. The release PR (`chore(main): release <version>`) is covered in `playbooks/shipping.md`. On it, `gh pr checks` reports no checks and the `CI` and `PR checks` runs sit at `action_required`, so there is no green to wait for.

**Reply:** each check and its state, what you fixed and in which commit, and what waits on the user.

Sources: .github/workflows/pr-checks.yml, .github/workflows/super-linter.yml, .github/workflows/new-module-proof.yml, docs/directives/git-and-prs.md, docs/verify/gate-checks.txt, docs/verify/quick-check.sh, docs/verify/new-module-proof.sh, docs/how-to/develop-locally.md, scripts/docs-stale.ts, scripts/names-check.ts, .claude/skills/byte-gh-issue-claim/SKILL.md, AGENTS.md
