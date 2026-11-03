### Authoring or modifying a skill

**Write it by the repo's `writing-for-agents` skill. Ship the skill's doc in the same PR.**

1. Check `skills-lock.json`. A skill listed there was installed from another repo (its `source`: `mattpocock/skills` or `Bytefloww1013/josh-skills`; `npx skills add <source> --skill <name> -a claude-code --copy`), and super-linter skips it because it is linted there: a new one is added to the `.claude/skills/(...)` list in `FILTER_REGEX_EXCLUDE` of `.github/workflows/super-linter.yml`. A skill written in this repo is not in the lock (`add-module`, `byte-docs-add`, `byte-docs-glossary`, `byte-docs-review`, `byte-handoff`).
2. Read the repo's `writing-for-agents` skill, then its `SKILL-MECHANICS.md` for frontmatter and the invocation choice.
3. Pick the invocation. Model-invoked: omit `disable-model-invocation` and put the trigger branches in `description`. User-invoked: set `disable-model-invocation: true` and write a one-line, human-facing `description`. Pick model-invocation only when the agent or another skill must reach the skill on its own.
4. Write the frontmatter the repo's skills use: `name`, `description`, `argument-hint` when the skill takes arguments, and `disable-model-invocation` when user-invoked. See `.claude/skills/byte-docs-add/SKILL.md` for a full example.
5. Prune by the `## Pruning` section of `writing-for-agents`: one home per meaning, no restating what `package.json` or config already says, and delete a no-op sentence whole (**principle-subtract-before-you-add**). A rule agents keep breaking goes in a check, and the skill points at it (**principle-encode-lessons-in-structure**).
6. Write or update the skill's doc at `docs/skills/<name>.md`. A new doc comes from the repo's `byte-docs-add` skill. It is user-invoked, so ask the user to run `/byte-docs-add skill <name>`. Docs are written by `docs/directives/writing-docs.md`. The doc has five sections in order: What it does and when it's used, Install, Run, Arguments, Gotchas. Install says `In this repo, no install.` for a skill written here, or the `npx skills add` line from the skill's lock entry. Arguments covers every argument in the skill's `argument-hint`.
7. For a new doc, run `bun run docs:gen`; it adds the doc to `docs/README.md` and to the index in `README.md`. After any skill or doc edit, run `bun run docs:check`: it fails a skill with no doc, sections out of order, an Install line that differs from the lock, and an Arguments section that leaves out an `argument-hint` argument.
8. Run `bun run docs:stale`. A skill doc's `sources` lists the skill's files (`.claude/skills/<name>/**` or its `SKILL.md`), and for an installed skill `skills-lock.json` too. A skill edit without a doc edit fails, and so does a `skills-lock.json` change for each installed skill's doc, unless the PR body has `docs-unaffected: <doc> - <reason>` for it. Locally the body is `tmp/pr-body.md`, and it must name the branch's issue (`#<N>`).
9. Open the PR per `playbooks/opening-a-pr.md` and `docs/directives/git-and-prs.md`. A past skill change: branch `chore/update-issue202-matt-skills`, PR title `chore(skills): update the vendored Matt Pocock skills and add software-factory`, merged as #203.
10. Before merge, the user can run `/byte-docs-review pr` to check the skill's doc against the skill. It is user-invoked and runs locally only.

**Not established in bphs-connect:**

- When a skill needs `agents/openai.yaml`, or what its fields mean. 39 of 48 skill folders have one; the nine without are `add-module`, `byte-docs-add`, `byte-docs-glossary`, `byte-docs-review`, `byte-gh-issue`, `byte-gh-issue-claim`, `byte-handoff`, `review-team` and `software-factory`.
- A way to test a skill's effect on agent behavior. See `playbooks/eval.md`.

**Reply:** what the skill does, its invocation choice, its doc path, and the checks run with their results.

Sources: skills-lock.json, .github/workflows/super-linter.yml, .claude/skills/writing-for-agents/SKILL.md, .claude/skills/writing-for-agents/SKILL-MECHANICS.md, .claude/skills/byte-docs-add/SKILL.md, .claude/skills/byte-docs-review/SKILL.md, docs/skills/byte-docs-review.md, docs/skills/retro.md, docs/README.md, docs/directives/git-and-prs.md, docs/directives/writing-docs.md, scripts/docs-stale.ts, scripts/docs/skills.ts
