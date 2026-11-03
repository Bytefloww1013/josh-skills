### Prototype

**You own the design decision, not the code. The prototype is throwaway. The real build follows Feature.**

Run the repo's `prototype` skill. It owns the method. This playbook adds the bphs-connect specifics.

1. Scope the question. No question means no prototype: route to `playbooks/feature.md`. A prototype is an experiment, not implementation, so it may run before the plan's go-ahead, during the question rounds (SKILL.md, "A feature plan"). The skill picks the branch:
   - "Does this logic or state model feel right?" goes to LOGIC.md: one shareable HTML file that a non-developer can drive.
   - "What should this look like?" goes to UI.md: several radically different variants (default 3, cap 5) switched by a `?variant=` search param and a floating bottom bar. This is the cheap way to compare competing designs (**principle-exhaust-the-design-space**).
2. Place it. Keep it next to the module or page it is for, and name it so a reader sees it is a prototype. UI.md prefers variants on an existing route. A new throwaway route follows the existing routing convention: each module's `web/routes/` is mounted under the app layout at its `routePrefix`.
3. Keep it disposable. No tests, no abstractions, state in memory. If the question needs a database, use a scratch one with a "PROTOTYPE, wipe me" name. Never a real backup or a copy of the live database (`docs/directives/production-safety.md`).
4. Make the observation the test. Surface the full state after every action or variant switch. To judge a UI variant against real data, start `docs/verify/scratch-server.sh start` (seeded, port 3388) and capture each variant with `node docs/verify/browser.mjs [--width <px>] <address>...`. Screenshots land in the ignored `tmp/browser` unless `--out` is given.
5. Present the variants, the evidence and a recommendation. Recommend the variant that best serves the work `PRODUCT.md`'s Product Principles put first (fast, keyboard-operable entry and trustworthy answers), even when another is cheaper to build (**principle-experience-first**).
6. Capture it. Fold the validated decision into the real code through Feature. Commit the prototype itself to a throwaway branch, out of `main`, and leave a pointer to that branch on the implementation issue. Record the verdict and the question it settled in the issue or a commit. `main` keeps only the decision.

Branch name: the `prototype` skill says only "a throwaway branch". The `ask-matt` skill names it `prototype/<name>`, but both vendored skills are "written for any repo, not this one" (`docs/skills/prototype.md`, `docs/skills/ask-matt.md`). AGENTS.md says to name every new branch by `docs/directives/git-and-prs.md`'s branch rule before its first commit, in place of any name you are handed, and that `bun run names:check` fails any other name; the directive's one exception is release-please's release PR. So name it `<descriptor>/<action>-issue<N>-<description>` (`issue<N>` is the issue the branch works): `prototype/<name>` fails `names:check`. The directive has no `prototype` descriptor, and which descriptor and action a prototype branch takes is not established in bphs-connect. Pick from the directive's lists and say which in the reply.

PR: the skill, AGENTS.md and the directive prescribe no PR for the prototype branch, only the commit and the pointer on the issue. Whether to push it is not established either; the directive says only never to push to `main`.

No precedent yet: the repo has no prototype folder and no prototype branch.

**Reply:** the question, the variants explored, the evidence (screenshots or observed state), tradeoffs, your recommendation, and the throwaway branch. Say plainly that the prototype is throwaway.

Sources: .claude/skills/prototype/SKILL.md, .claude/skills/prototype/UI.md, .claude/skills/prototype/LOGIC.md, .claude/skills/ask-matt/SKILL.md, AGENTS.md, docs/directives/git-and-prs.md, scripts/names-check.ts, docs/skills/prototype.md, docs/skills/ask-matt.md, docs/directives/production-safety.md, docs/references/architecture.md, docs/verify/scratch-server.sh, docs/verify/browser.mjs, PRODUCT.md
