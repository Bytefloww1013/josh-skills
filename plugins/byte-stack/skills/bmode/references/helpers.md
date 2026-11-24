# Helpers

Use this reference when a playbook step names a byte-stack helper or an arch-skills skill, or when you are about to offer one.

## byte-stack helpers

The byte-stack helper skills ship next to bmode, at `../<name>/SKILL.md` relative to bmode's folder. Bmode names each one by its Skill ID, `byte-stack:<name>`.

- **Run a model-invocable helper** (Skill tool column below): invoke its Skill ID with the Skill tool. If the Skill tool can't load it (a delegate on a non-Claude model, or a session without byte-stack installed), Read its `SKILL.md` and follow it.
- **Run a user-invoked helper** (Read column): open its `SKILL.md` with Read and follow it as that step. Open the references and other helpers it names the same way. The user's `/bmode` is the say-so for those runs, so the user-invoked skill rule in `SKILL.md` (Non-negotiables) does not apply to them.
- **Offer.** When a step says to offer a helper, leave the run to the user: ask them to run `/byte-stack:<name>`.
- **Precedence.** The repo's rules and gates win over a helper, as they do over a principle.

| Skill ID | Run with | Use it when |
| --- | --- | --- |
| `byte-stack:how` | Skill tool | You need a working model of a subsystem before you change it, or a "how does X work" answer. |
| `byte-stack:blast-radius` | Skill tool | A change reaches a public API, hook, slot, migration or the kernel, or you don't fully trust a diff. It fills the PR body's Blast Radius line. |
| `byte-stack:architect` | Skill tool | A design choice has no precedent. It builds two plans and picks one with the arch-skills reviews. |
| `byte-stack:figure-it-out` | Skill tool | A large or multi-part task matches no playbook. It designs and runs one. |
| `byte-stack:technical-writing` | Skill tool | You write a doc, an ADR, a PR body or a commit message ([writing.md](writing.md)). |
| `byte-stack:unslop` | Skill tool | Before any reply or written text goes out. |
| `byte-stack:typescript-best-practices` | Skill tool | You write or review `.ts` or `.tsx` code, with `byte-stack:principle-type-system-discipline`. |
| `byte-stack:docs-add` | Skill tool | You create a doc ([triggers.md](triggers.md), "A doc"). |
| `byte-stack:docs-review` | Skill tool | A PR changes code a doc describes (Shipping, Opening a PR). |
| `byte-stack:gen-issue` | Skill tool | You file a GitHub issue ([triggers.md](triggers.md), "A GitHub issue"). |
| `byte-stack:sol-loop` | Skill tool | Under T3, the Opening a PR playbook's Sol review ([t3-model-routing.md](t3-model-routing.md)). |
| `byte-stack:in-your-own-words` | Skill tool | The first question round of a plan (Multi-phase plan, Feature), or a request that could be read more than one way. |
| `byte-stack:swarm` | Read | A step names it for parallel workers. |
| `byte-stack:sharpen` | Read | A step names it to make a task deeper before you start. |
| `byte-stack:correct` | Read, or offer | A class of mistake has come up twice (`byte-stack:principle-encode-lessons-in-structure`). |

Per-helper rules:

- **Cost.** `architect`, `swarm`, `figure-it-out` and the complex path of `how` each start several subagents. Run them only at the steps that name them, under each step's condition.
- **Handoffs.** In bphs-connect, `byte-handoff` is the repo's own copy (`.claude/skills/byte-handoff`), so invoke it as `byte-handoff`, not through byte-stack (the Pause safely playbook).
- **`architect`.** It builds two plans, reviews them with `arch-skills:architecture-review-report` and `arch-skills:architecture-decision-review`, and stops at its Phase 6 hand-off with `final-plan.md` and `decision.md`. Under a feature plan, the go-ahead is the checkpoint:
  1. Run Phases 1 to 6 during the question rounds.
  2. Put `final-plan.md`'s Selection and shape in the plan's `## Decisions`, with the ADR draft from `decision.md` (arch-skills, below).
  3. Run Phase 7 (implement) only after the go-ahead.
  Its decision review is the step's `architecture-decision-review` run, so don't run a second one on the same choice. The plan is never committed, so the PR body's `## What and why` carries the selection.
- **`figure-it-out`.** Under a feature plan, its decision log lives in the plan's `## Decisions`. Put what a reviewer needs from the log in the PR body, since the plan is never committed (`docs/directives/plans.md`).
- **`council-review`.** Only the user starts it, by saying "council". No playbook step runs it, not even before a PR. When the direction of a change looks uncertain, you may suggest it in one line.

## arch-skills

bphs-connect's `.claude/settings.json` turns on the arch-skills plugin from `Bytefloww1013/josh-skills`. Its four skills are model-invocable.

- **How to run one.** When a step names one, run it through the Skill tool as `arch-skills:<name>`, not with Read.
- **Profile.** Each skill reads its profile of this repo (`references/project-bphs-connect.md`) first. The repo's rules and gates win over the skill and over that profile (`docs/skills/arch-skills.md`).
- **Under T3.** When Antigravity offers Gemini 4 Neon, `architecture-decision-review`, `architecture-review-report` and `repo-navigability-audit` run on Neon as T3 delegates, and `pr-erosion-check` stays in this session ([t3-model-routing.md](t3-model-routing.md)). Everything below applies either way.

### `architecture-decision-review`

- **When it runs:** in the Feature, Multi-phase plan, Refactoring and New migration playbooks, before a design choice that adds, splits or moves a module, table, public API, hook, slot or dependency.
- **Mode:** quick mode for a two-way door, full mode for a one-way door.
- **Scope:** it decides and records one choice. When the choice has no precedent, `architect` builds two competing plans and runs this review across them, and its `decision.md` is the record (Exhaust the Design Space).
- **Output:** its decision goes in the plan's `## Decisions`, and from there into the PR body's `## What and why`.
- **ADR draft:** the skill writes its ADR draft into `docs/adr/` by itself. Keep the draft in the plan instead, in the repo's ADR format with status proposed. Write the file only on the user's yes.

### `architecture-review-report`

- **When it runs:** on a written plan before you ask for the go-ahead, and on a set of issues before a queue run starts.
- **Output:** put its report under `tmp/` or in the reply, never in the repo.
- **Findings:** answer each Critical or High finding in the plan. Answer it in the issue only on the user's yes, since an edit there posts outside the repo. Put each Gap to the user as a question.
- A clean report is not the go-ahead.

### `pr-erosion-check`

- **What it is:** the architecture-and-scope merge verdict, with the issue as the yardstick.
- **When it runs:** opening a PR runs it on the branch against `origin/main` before the push, fixes its Critical and High findings, and puts the verdict under `## How it was checked`. The coordinator of a queue run also runs it on each delegate's PR before the merge.
- CLEAN is not the user's word to merge.
- The three review agents keep their own triggers ([triggers.md](triggers.md), Review agents), `code-review` keeps Standards and Spec, and `review-team` stays the wide review.

### `repo-navigability-audit`

- **When it runs:** on request, or offered when reviews keep finding copied helpers (Encode Lessons in Structure), then run on the user's yes.
- It moves no file. Its fixes and its AGENTS.md draft wait for the user.

### Shared notes

- **Cost.** Each skill runs its own Python 3 scripts and reads only the references its triage picks. Full-mode decision review and a whole-repo audit take the longest. `pr-erosion-check` may start one subagent to confirm a Critical or High finding ([subagents.md](subagents.md)).
- **The reminder hook.** Before `gh pr create`, the plugin reminds you to run `pr-erosion-check`. The Opening a PR playbook has already run it, so carry on. The hook is not the user's say-so to open the PR.
- **Unavailable.** A cloud session installs no plugins, so neither the skills nor the hook are there. Say so in the reply, skip the step, and continue with the review agents and `code-review`.
