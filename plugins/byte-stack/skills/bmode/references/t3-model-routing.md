# Model routing under T3

Applies when the run is inside T3 Code (the `mcp__t3-code__*` tools exist) and the coordinator is the main thread (T3 children start no subagents). Call `orchestrator_capabilities` once per thread. A model counts as available only when it is listed under a provider with `canRunChildTask: true`; capabilities also lists models under disabled providers. Outside T3, every scout, reviewer and implementor is a Claude `byte-agent` on Opus, as SKILL.md says, and the reply says so under Helpers. Named agents (the review agents, the byte-docs agents) still launch by name.

## Which model: the policy

bphs-connect's `docs/agents/sub-agent-choice.md` is the policy for the three delegate roles. It lists the models for each role in order, with a level for each, and says when a job is critical. Read it at the root of the coordinator's checkout before the first dispatch of a run. This file adds only how to apply it under T3. Where the two disagree, the policy wins, and this file is fixed to match.

| Role in the policy | What it covers here | Brief |
| --- | --- | --- |
| Scout | The bulk reads Guard the Context Window hands to a subagent (a log, HAR, trace, transcript, wide diff), an investigation's search after CodeGraph, a trace-forensics parse, a question the dispatch loop sends, and `gen-issue`'s Decider | `briefs/scout.md`; the Decider `briefs/gen-issue-decider.md` |
| Reviewer | The reviewer brief in the dispatch loop, the review agents `access-reviewer`, `migration-reviewer` and `module-boundary-reviewer`, and `docs-review`'s `byte-docs-review-finder` and `byte-docs-review-refuter` | `briefs/reviewer.md`; a review agent takes the named-agent template below; the docs-review agents `briefs/docs-review-finder.md` and `briefs/docs-review-refuter.md` |
| Implementor | The code-writing delegate that builds one ticket (Orchestrate step 4) | `briefs/implementor.md` |

A job is critical when its issue is labelled `one-way-door` or the job is important, and non-critical when its issue is labelled `two-way-door`. With no issue, the coordinator judges, and treats a migration, an access change or a data change as important.

The policy doesn't cover these, so they route as follows:

| Step | Model | How |
| --- | --- | --- |
| `arch-skills:architecture-decision-review`, `architecture-review-report`, `repo-navigability-audit` | Gemini 4 Neon, by the Gemini tier below | `delegate_task`, role `review`, isolation `shared`, mode `async`, the arch-skill template below |
| `byte-docs-glossary`'s drafter and auditor | Gemini 4 Hydrogen, `high` | `delegate_task`, role `review`, isolation `shared`, mode `async`, the named-agent template below |
| `byte-docs-glossary`'s refuters | Gemini 4 Neon, by the Gemini tier | same |
| The Sol review before the push | Sol, as its section below says | `byte-stack:sol-loop` |

Not routed: `codegraph_explore` (still first for code), `pr-erosion-check`, Decision subagents, `review-team` reviewers and byte-stack helpers' runners.

## Usage left

The policy runs the first model that is available and has usage left. Before each routed step, run `python3 -I <byte-stack>/skills/council-review/scripts/provider-usage.py` (the folder next to bmode's). It never prints a token.

- **Gemini** (Neon, Hydrogen): the user has two Antigravity accounts with separate usage, T3 provider instances `antigravity` and `antigravity_2`. Each has a row: `gemini` for `antigravity`, `gemini:antigravity_2` for the second, each the tighter of its 5-hour and weekly windows. Use `antigravity` while its row has usage left; when it is at 0%, or a delegate on it fails on a usage limit, start the same model on `antigravity_2` (same target, `providerInstanceId: "antigravity_2"`), and only when both are out go down the policy's list. A row reading `unknown` with `verify the account` means Google wants the user to verify that account (a 403, the sign-in link is in its `antigravity-acp/log/acp-server-*.log`): tell the user and skip that account. At 50% or more, Neon runs at the higher level the policy gives; from 1% to 49%, at the lower one (`medium` where the policy gives "high or medium"). At 0%, skip Neon and Hydrogen. If the row reads `unknown`, ask the user once for the level and keep the answer for the run.
- **Sol**: its `codex` row. The Sol review section below gives the levels.
- **OpenCode** (DeepSeek V4.1 Flash 1017, Tencent Hy4): runs through the homelab T3 server's `opencode` provider. No reader exists for its usage, so count it as available while `orchestrator_capabilities` lists the model.
- **Claude** (Opus, Haiku): no reader exists either. Where the policy depends on Claude's usage (Opus as a non-critical implementor), ask the user once how much of Claude's 5-hour and weekly usage is left, and keep the answer for the run.

Where the policy gives two levels, pick by how hard the task is and the usage left.

A delegate that fails because a usage limit has been reached marks that provider gone for the rest of the run: rerun the step on the next model in the policy's list and say so in one line (for Gemini, first on the other Antigravity account, as Usage left says). Antigravity's text, seen on 23 Nov 2026, is `Individual quota reached. Please upgrade your subscription to increase your limits. Resets in <h>h<m>m<s>s.` (HTTP 429 `RESOURCE_EXHAUSTED`); an account Google wants verified answers `⚠ Verification Required` (HTTP 403, `Verify your account to continue.`), which counts as that account unavailable, not as a usage limit. Any other failure is reported to the user, and the coordinator does not switch models on its own (T3 rule).

## Starting a delegate

Fill the brief with `briefs/fill-brief.py` (the dispatch loop says how) and pass the printed brief as the whole `task`.

- **Claude models** run on the Agent tool, as T3 asks for a child on the coordinator's own provider: a `byte-agent` with `model` and `effort` from the policy (`claude-opus-5-5` at `high` is `model: "opus"`, `effort: "high"`), `run_in_background: false`, and `isolation: "worktree"` for an implementor. A docs-review agent launches by name instead, so its file's `tools:` line holds, and the Decider as a `general-purpose` agent; each takes the filled brief as its prompt. `--provider claude` in the filler.
- **Other models** run through `delegate_task`, with the target in the shape `orchestrator_capabilities` lists, from the model-id table in the policy: `{ providerInstanceId: "antigravity", model: "gemini-4-neon", options: { thought_level: "high" } }`, or a per-level id (`gemini-4-neon-high`) with no options where capabilities lists one. T3 switched from the second shape to the first on 20 Nov 2026, and a table that named only one shape sent every step to Opus. A scout takes role `research`, isolation `shared`; a reviewer role `review`, isolation `shared`; an implementor role `implementation`, isolation `worktree`; all mode `async`. Follow each delegate's `next`, and don't poll it. `--provider antigravity`, `opencode` or `codex` in the filler.

CodeGraph: T3's Antigravity children don't get the CodeGraph MCP tool, so the filler gives every non-Claude delegate the `codegraph explore` CLI. A probe on 20 Nov 2026 (Neon High, its own worktree) read all of bmode's `SKILL.md`, a playbook and a principle leaf from the coordinator's plugin cache by absolute path, and ran `bun install`, `vitest`, `gh` and the `codegraph` CLI there. OpenCode and Codex children have not been probed.

## When an implementor fails

The coordinator judges every implementor's branch the same way, and trusts nothing in its report it hasn't rerun (Orchestrate steps 5 and 6): `docs/verify/quick-check.sh` in the worktree, the steps the report lists as pending (such as `blast-radius` for a refactor, with its result in the PR body), `pr-erosion-check`, the review agents the change meets, and the Sol review before the PR is opened. The push and the PR stay the coordinator's.

A branch an implementor left red, or whose report the coordinator's checks contradicted, counts as a failed run: the next model in the policy's list builds the ticket, and no model that failed the ticket gets it again in this run. Before that delegate starts, free the ticket's branch name and keep the failed work for the report: in the failed worktree, `git branch -m <branch> <branch>-<model>`. Keep that worktree and branch, which may hold commits nothing else has, until the user says to discard them. On that word, remove them even though the branch was never merged (`git worktree remove <path>`, then `git branch -D <branch>-<model>`); Worktree cleanup's stop for uncommitted work still holds, so report a dirty worktree instead of forcing it.

## Sol review before the push

Applies when the run is inside T3, the coordinator is the main thread, and `orchestrator_capabilities` lists provider `codex` with `canRunChildTask: true` and a Sol model (pick the latest `gpt-*-sol`). The `codex` row of `provider-usage.py` sets the effort:

| `codex` 5h remaining | Sol effort                                      |
| -------------------- | ----------------------------------------------- |
| 30% or more          | `reasoningEffort: high`                         |
| 1% to 29%            | `reasoningEffort: medium`                       |
| 0% (limit gone)      | none: `code-review` on Claude, and say so       |
| `unknown`            | `reasoningEffort: medium`, with the fallback below |

When it applies, Opening a PR step 7 runs `byte-stack:sol-loop` on the branch against `origin/main` after `pr-erosion-check` and before the PR is opened, with sol-loop's own budget and brief. Commit each fix it leads to as step 7 commits an erosion fix, rerun `docs/verify/quick-check.sh`, and check that the commit being pushed holds the diff Sol last reviewed. sol-loop hands its outcome back here: the playbook's push and PR rules apply, not sol-loop's step 5 push rule. Later pushes to the same PR (a babysit fix, a review answer) get no new Sol round unless the user asks. The coordinator runs it for each delegate's branch too, since T3 children start no reviewers. Sol is the change's code review: it takes the place of `code-review`'s Standards and Spec sub-agents wherever a playbook names them, and of any extra fresh Claude review round. The review agents keep their triggers and the routing above.

- APPROVE on the current diff: carry on to the title, push and merge rules as before.
- The budget ends with a blocker or should open: push and open the PR as the playbook allows, but don't merge it. Put a `Sol hold:` line with each open finding under `## How it was checked`, and flag it to the user with both sides. The hold lasts until the user clears it or a later Sol round approves the PR's current diff; the coordinator then deletes the line from the PR body and says which cleared it.
- A Sol delegate that fails on the usage limit sets the tier to gone for the run: run `code-review` instead and say so in one line.

Why: Sol and Gemini are there to take review work off Claude (the user, 20 Nov 2026). Before this section, Sol ran only when a prompt named `sol-loop`, so from 19 Nov every review ran on Claude while the `codex` window sat unused.

## The brief

The child sees only `task`. A scout, reviewer or implementor, a docs-review agent and the Decider get their brief from `briefs/fill-brief.py`. A review agent or a `byte-docs-glossary` agent on a non-Claude model gets the named-agent template, and an arch-skill run the arch-skill template, each filled in by hand.

The coordinator acts on what comes back exactly as SKILL.md's arch-skills section says: it answers Critical and High findings, puts Gaps to the user and keeps the ADR draft in the plan. A verdict from any model counts the same as one from Opus. It is never the go-ahead and never the word to merge.

### Template: arch-skill

```text
You are running the arch-skills skill `<name>` in the bphs-connect checkout at <path>. Run it
from the arch-skills plugin you have loaded. If you can't invoke it, Read its SKILL.md in full
from your plugin folder: `$GEMINI_HOME/config/plugins/arch-skills/skills/<name>/`, else
`~/.gemini/config/plugins/arch-skills/skills/<name>/`. Read its profile
references/project-bphs-connect.md first, as the skill says. AGENTS.md maps the Claude tool names to
Antigravity's. Use CodeGraph (`bphs-codegraph_codegraph`) before you read code.

Target: <plan path | issue numbers | base origin/main and branch | "the repo">.

Rules (these win over the skill):
- Write nothing in the repo except one report at tmp/arch/<name>-<timestamp>.md.
- Do not write an ADR file in docs/adr/. Put the ADR draft in the report, status proposed.
- Move, rename or delete no file. Don't commit, push, open or comment on any issue or PR.
- Start no subagents.

Reply with: the report path, the verdict or counts (Critical/High/Medium/Low, Gaps), and each
Critical and High finding in one line with its quote.
```

### Template: a named agent

```text
Act as the `<agent>` agent. Read .claude/agents/<agent>.md in <path> in full. Its body is your
instructions, and its `tools:` line is your limit: use only your own equivalents of those
tools (AGENTS.md maps them for Antigravity). For code, run `codegraph explore "<query>"` first. <If the agent has no Write tool:> Change no file. <If it writes:>
Write only under <absolute scratchpad path>. Start no subagents.
<Exactly the input the skill gives this agent, and nothing more: base, the diff pasted or the
absolute path of a file holding it, term, findings file…>
Reply in the format its file asks for.
```

A file path beats pasting the definition: the file stays the one source, and the brief stays short. No provider but Claude enforces a `tools:` frontmatter, so the brief states the limit. On Claude, launch the agent by name with the Agent tool instead.

**A named agent.** The delegate takes the place of the skill's "launch agent X" step, and everything else in the skill stays the same. Keep each skill's information barrier: a refuter gets only what the skill gives it (for example, `byte-docs-glossary-refuter` gets only each term and its definition), so each agent is a separate delegate with its own brief. Some of these agents are not read only. The glossary drafter and auditor write their findings to the scratchpad, and `byte-docs-glossary-refuter` has every tool. So the brief gives the absolute scratchpad path, and gives each agent the same tool limit its file sets. A review agent's format has no severity scale, so the coordinator sets each finding's severity itself.

## Report

Under Helpers, each routed step says which model ran it, at what level, and why. For example:

- Scout for #712: DeepSeek V4.1 Flash 1017 (max), first in the policy.
- `access-reviewer` on #713, critical: `gpt-6.2-sol` (high), `codex` 81%.
- #712 implementor, non-critical: Gemini 4 Neon (high), `gemini` 81%; quick-check PASS on the coordinator's rerun.
- `architecture-review-report`: Gemini 4 Neon (high), tier ≥50%: 0 Critical, 2 High, 1 Gap.
- Sol review: `gpt-6.2-sol` (high), `codex` 100%: 2 rounds, APPROVE, 1 should fixed.

## Why these models: the bake-off of 19 Nov 2026 (Neon High and Hydrogen High; the reference is what the Claude reviewer found)

| PR | Agent | What Claude found | Neon High | Hydrogen High |
| --- | --- | --- | --- | --- |
| #662 | `module-boundary-reviewer` | `Signer` and its words in the kernel (Low to Medium) | Caught it, rated High. Same fix, plus the doc line to change. | Caught it, and labelled it "Severity 1" (the agent's format has no scale). Same fix. |
| #668 at `3d80641b72` | `access-reviewer` | (1) `heldLink()` could be attached outside the link routes; (2) a throwing `onLock` undid the fifth strike | Caught (1), rated Low. Missed (2). Found one more real Low that is still on `main`: `actOnLink` validates the body before it checks eligibility, so a holder gets a 422 where they should get a 403. | `no findings`. Missed both. It read the right commit: its line numbers match `3d80641b72`. |

The four runs used about 26% of the Gemini 5-hour window (85% → 59%), about 6% a review. An eight-auditor glossary audit on Gemini would take about half the window.

The sample is small: two PRs, one agent each. `migration-reviewer`, the `byte-docs` agents and refuters on Neon have not been tested. Gap (2) is confirmed by `45d8817c9e`, which fixed it after `3d80641b72`.

Before the policy file (22 Nov 2026), these results kept `access-reviewer` and `migration-reviewer` on Claude. The policy now puts Sol first for them. Sol hasn't been tested on either agent, so watch the first few runs against a Claude rerun.
