### Eval

**bphs-connect has no harness to measure how a skill change moves agent behavior. Say so, then run the checks it has.**

Not established in bphs-connect: eval or benchmark tooling for skills or the repo (no eval or bench scripts, `package.json` entries, directories or files).
Not established in bphs-connect: a script, test or CI step that checks what the `writing-beats`, `writing-fragments` or `writing-shape` skills make an agent do. `docs:check` reads only their docs and `argument-hint` (`scripts/docs/skills.ts`).
Nothing runs AI in CI (`docs/skills/byte-docs-review.md`).

1. Tell the user no eval harness exists. The checks below cover the skill's doc, not the agent's behavior.
2. Run `bun run docs:check` and `bun run docs:stale`. `docs:check` fails when `docs/skills/<name>.md` lacks its five sections, its Install line or an argument named in the skill's `argument-hint` (`scripts/docs/skills.ts`). `docs:stale` fails when the skill's files changed but `docs/skills/<name>.md` did not, unless the PR body has `docs-unaffected: <doc> - <reason>`. Locally it diffs against `origin/main` and reads the PR body from `tmp/pr-body.md` (or `--body-file <file>`). CI runs it on each PR to `main` as `Stale docs`.
3. Run the `byte-docs-review` skill as `pr` (`pr --base origin/main` when the branch has no PR yet), with the permission its first lines ask for. It needs `gh` logged in, and runs the script checks first. `--no-post` prints the findings instead of posting a PR comment. It runs locally only, so its findings never block a merge.
4. When the question is whether a sentence changes behavior, `writing-for-agents` says to settle it by running the document, not by debate (`## Pruning`). The repo gives no harness for that run, so run it through the **swarm** helper: two race arms on the same task, one with the sentence and one without, the same number of workers in each, `rank all` declared and the done predicate fixed before the fan-out. Report what every run did, whether every run did the task, and whether the difference held across runs (**principle-explain-the-number**).

**Closest patterns in the repo:**

- `byte-docs-review`: a `byte-docs-review-finder` agent quotes each finding, `bun run docs:quote-check` drops findings whose quotes are not real, and a fresh `byte-docs-review-refuter` agent that never sees the finder's `why` or reasoning answers `upheld` or `refuted`.
- `byte-docs-glossary`: its `byte-docs-glossary-refuter` agent has no tools and never sees the evidence, and `audit` launches eight `byte-docs-glossary-auditor` agents in one message, one lens (`grounding` or `clarity`) and one group each.
- `retro`: after a session, suggests changes to the agent's environment, including no-op lines in steering files. It runs only when called by name and does not know this repo's directives.

**Reply:** the change under test, the checks run with their results, the swarm's runs when step 4 ran, and a plain statement that bphs-connect has no eval harness.

Sources: package.json, scripts/docs-stale.ts, scripts/docs/skills.ts, .github/workflows/pr-checks.yml, docs/directives/git-and-prs.md, .claude/skills/byte-docs-review/SKILL.md, docs/skills/byte-docs-review.md, .claude/agents/byte-docs-review-finder.md, .claude/agents/byte-docs-review-refuter.md, .claude/skills/byte-docs-glossary/SKILL.md, .claude/agents/byte-docs-glossary-refuter.md, .claude/agents/byte-docs-glossary-auditor.md, .claude/skills/writing-for-agents/SKILL.md, .claude/skills/retro/SKILL.md, docs/skills/retro.md
