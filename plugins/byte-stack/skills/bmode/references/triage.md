# triage

Use this reference when the Babysit playbook (`../playbooks/babysit.md`) meets a comment on a PR.  Otherwise, you can call the matt pocock skill `/triage`.

## What a PR gets

- **Super-linter summary**, from `github-actions[bot]`. The `Super-Linter` job posts it on PRs (`ENABLE_GITHUB_PULL_REQUEST_SUMMARY_COMMENT: true` in `.github/workflows/super-linter.yml`). It starts with `<!-- super-linter-summary-comment -->`. The job is skipped when `ci:scope` finds the change is `text` or `tested`, so a Markdown-only PR gets no summary. The `github-actions` login wrote 99 issue comments across the 105 PRs.
- **Oxlint annotations**, from the `Typecheck, test, build` job: `bun run lint --format github` turns each finding into an annotation on the PR (`.github/workflows/super-linter.yml`). They are not comments.
- **Created releases**, a `🤖 Created releases:` comment from `github-actions[bot]` (release-please, `.github/workflows/release.yml`) on a merged release PR. #229 got one for `v1.2.0`.
- **byte-docs-review findings**, when the `byte-docs-review` skill runs as `pr`. The skill posts them with `gh pr comment <n> --body-file`. The post holds a summary line, a findings table, and the marker `<!-- byte-docs-review:findings -->` with the findings as JSON.
- **The owner's comments.** The owner wrote 2 issue comments across the 105 PRs.

## How to handle each

- **Super-linter summary.** It reports the `Super-Linter` job. Treat the job's result as the verdict. "All files and directories linted successfully" needs nothing. On a PR, Super-Linter lints only the changed files. TypeScript is left to the `Fast checks` and `Typecheck, test, build` jobs. Fix a reported error in this PR's files, then let the job rerun.
- **Created releases.** Nothing to do.
- **byte-docs-review findings.** Each finding already passed `bun run docs:quote-check`, which drops a finding whose quotes are not real, and a refuter that upholds only what the code proves. The findings are the user's to act on. Fix nothing unless the user asks. If they do, the fix goes in the same PR, since a change updates the docs it makes stale in the same PR (`docs/directives/git-and-prs.md`). Rerun the skill only with the permission its first lines ask for. `bun run docs:drift-report` finds posted reviews by their marker.
- **A comment from the owner or another person.** Not established in bphs-connect: a rule for answering one. Ask the user.

Not established in bphs-connect: a rubric of dismissal patterns. No bot posts findings that need one.

Sources: .github/workflows/super-linter.yml, .github/workflows/release.yml, docs/directives/git-and-prs.md, .claude/skills/byte-docs-review/SKILL.md, .claude/agents/byte-docs-review-refuter.md, docs/skills/byte-docs-review.md, scripts/docs/findings.ts
