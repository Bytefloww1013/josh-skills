# Subagents

Use this reference before you spawn a subagent under bmode, or when a helper sends you here to pick a subagent's model or reasoning level.

Hand bulk reads to subagents as Guard the Context Window says. Split their write targets as Separate Before Serializing Shared State says ([principles.md](principles.md)). The repo sets subagent rules only inside its skills and agents. Find the skill or agent you are running below and follow its line.

## Model, brief and routing

- **Scouts, reviewers and implementors.** bphs-connect's `docs/agents/sub-agent-choice.md` is the policy for which model runs each role, tried in order. [t3-model-routing.md](t3-model-routing.md) applies it under T3.
  - Fill every brief for these roles with [briefs/fill-brief.py](briefs/fill-brief.py).
  - Check each report with [briefs/check-report.py](briefs/check-report.py).
  - Route between them by [dispatch-loop.md](dispatch-loop.md).
- **byte-stack helpers** ([helpers.md](helpers.md)). Spawn each subagent a helper starts as a `byte-agent`, so it reads bmode's `SKILL.md` first: an architect planner or reviewer, a how explorer or explainer, a swarm worker.
  - Pick each one's model from `docs/agents/sub-agent-choice.md` by its role, as the line above says. Architect planners and swarm workers take the implementor role. How explorers take the scout role. Architect reviewers and how explainers take the reviewer role.
  - A policy entry written as `<model>-<level>` means the Agent tool's `model` set to that model's family and `effort` set to the level. For example, an entry ending in `-xhigh` is `effort: "xhigh"`.

## Repo skills and agents

- **`byte-gh-issue-claim --auto`.** One Decision subagent per gate question (Agent tool, fresh context), with a batch's questions in one message.
  - It is read only. It replies `DECISION:` / `OPTIONS:` / `PROOF:`, or `STOP:`.
  - Print each reply verbatim under `### Decision: <gate>`.
  - In the plan's Ownership table, shared files (lockfiles, manifests, CI config, CLAUDE.md/AGENTS.md, the plan) belong to `main`.
- **`docs-review`** (byte-stack). One `byte-docs-review-finder` agent, or two or three for a large bundle. Its findings pass `bun run docs:quote-check`, then go to a `byte-docs-review-refuter` agent that never receives the finder's `why` or reasoning. Under T3, both follow the policy's reviewer role, with the briefs [briefs/docs-review-finder.md](briefs/docs-review-finder.md) and [briefs/docs-review-refuter.md](briefs/docs-review-refuter.md).
- **`gen-issue`** (byte-stack). With `--grill`, a fresh Decider per question. Under T3 it follows the policy's scout role, with the brief [briefs/gen-issue-decider.md](briefs/gen-issue-decider.md).
- **`byte-docs-glossary`.** One `byte-docs-glossary-drafter` agent, then a `byte-docs-glossary-refuter` agent given only each term and definition. `audit` launches eight `byte-docs-glossary-auditor` agents in one message, each with one lens (`grounding` or `clarity`) and one group, then a `byte-docs-glossary-audit-refuter` agent.
- **`review-team`.** A fleet of reviewer subagents against the same change, with prompts in `reviewers/`.
  - Mode `single` by default. Use `iterate` only when the user asks for it, and stop when more rounds bring no material new findings.
  - Tell each reviewer it cannot see the others.
- **Agents in `.claude/agents/`.**
  - The review agents `module-boundary-reviewer`, `migration-reviewer` and `access-reviewer` are read only, with the tools Read, rg, Glob and `codegraph_explore`. Each answers `no findings`, with the files it read, when no rule is broken.
  - The six `byte-docs-*` agents there belong to `byte-docs-glossary` and byte-stack's `docs-review`, which launch them by name.
  - Under T3, the three review agents and the two `byte-docs-review-*` agents run on the policy's reviewer model, and the four `byte-docs-glossary-*` agents run on Gemini, each as its own delegate ([t3-model-routing.md](t3-model-routing.md)).
- **`pr-erosion-check`** (arch-skills). For a large PR, or a Critical or High finding that rests on judgment, start one fresh subagent given only the restated claim, the hunk and the principle. The finding stays only if it agrees. For a boundary finding, the `module-boundary-reviewer` agent is that check (the skill's profile names it).

## Vendored skills

- **`code-review`.** Two sub-agents in parallel, issued together in the foreground, each brief under 400 words.
- **`improve`.** Read-only subagents over its audit areas. `execute <plan>` starts one `general-purpose` executor subagent with `isolation: "worktree"`, on `sonnet` unless the user names a model, then reviews its diff. Merging that work is the user's call.
- **`wayfinder`.** One fresh subagent per research ticket. It runs the `research` skill and pushes a throwaway `research/<name>` branch with no PR.
- **`grilling`.** A fresh sub-agent finds each fact the questions need, so the user is asked only for decisions.
- **`codebase-design`** (`DESIGN-IT-TWICE.md`). Three or more sub-agents in parallel, each with a fresh context window.
