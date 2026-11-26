# Original Byte Stack package

Baseline commit `6bbe7bd206116eb1dc8a116be085ca99169fe0a8`. The tar contains every original plugin file and mode, plus the original root README and Claude marketplace listing. Git retains their original history at that commit. The tar stays outside skill discovery.

Extract selected members into a separate directory, for example:

```sh
tar -xf archive/bphs-connect/byte-stack/6bbe7bd/source.tar -C /path/to/empty-directory plugins/byte-stack/skills/bmode/playbooks/upgrade-staging.md
```

To reuse a procedure, adapt its prerequisites and commands and place the result under the target worktree’s `.byte-stack/`. Supply a `Use when: ` description for any new playbook. Original policy files may refer to additional resources owned by the target repo.

## Disposition

Paths below are relative to the archived plugin root. Every original is recoverable from source.tar. The complete original Git tree is `9eb4fbe94b00bf3f8f82cd223d7c6926bb3ebfb8`.

| Original file | Active successor |
| --- | --- |
| `.antigravity-plugin/plugin.json` | Same path |
| `.claude-plugin/plugin.json` | Same path |
| `README.md` | Same path |
| `agents/byte-agent.md` | Same path |
| `hooks/check-handoff-guard.py` | Same path |
| `hooks/handoff-guard.py` | Same path |
| `hooks/hooks.json` | Same path |
| `skills/architect/SKILL.md` | Same path |
| `skills/architect/references/design-red-flags.md` | Same path |
| `skills/architect/references/plan-template.md` | Same path |
| `skills/architect/references/planner-prompt.md` | Same path |
| `skills/architect/references/review-and-pick.md` | Same path |
| `skills/blast-radius/SKILL.md` | Same path |
| `skills/bmode/SKILL.md` | Same path |
| `skills/bmode/playbooks/authoring-a-skill.md` | Same path |
| `skills/bmode/playbooks/autonomous-run.md` | Same path |
| `skills/bmode/playbooks/autopilot-full.md` | Same path |
| `skills/bmode/playbooks/autopilot-stack.md` | Same path |
| `skills/bmode/playbooks/babysit.md` | Same path |
| `skills/bmode/playbooks/bug-fix.md` | Same path |
| `skills/bmode/playbooks/eval.md` | Same path |
| `skills/bmode/playbooks/feature.md` | Same path |
| `skills/bmode/playbooks/hillclimb.md` | Same path |
| `skills/bmode/playbooks/investigation.md` | Same path |
| `skills/bmode/playbooks/multi-phase-plan.md` | Same path |
| `skills/bmode/playbooks/new-migration.md` | Same path |
| `skills/bmode/playbooks/opening-a-pr.md` | Same path |
| `skills/bmode/playbooks/orchestrate.md` | Same path |
| `skills/bmode/playbooks/pause-safely.md` | Same path |
| `skills/bmode/playbooks/perf-issue.md` | Same path |
| `skills/bmode/playbooks/prototype.md` | Same path |
| `skills/bmode/playbooks/refactoring.md` | Same path |
| `skills/bmode/playbooks/runtime-forensics.md` | Same path |
| `skills/bmode/playbooks/session-pickup.md` | Same path |
| `skills/bmode/playbooks/shipping.md` | Same path |
| `skills/bmode/playbooks/trace-forensics.md` | Same path |
| `skills/bmode/playbooks/upgrade-production.md` | Archived project or provider policy |
| `skills/bmode/playbooks/upgrade-staging.md` | Archived project or provider policy |
| `skills/bmode/playbooks/visual-parity.md` | Same path |
| `skills/bmode/playbooks/worktree-cleanup.md` | Same path |
| `skills/bmode/references/autonomy.md` | Portable routing in `skills/bmode/SKILL.md` and `references/subagents.md`; original project rules archived |
| `skills/bmode/references/briefs/check-report.py` | Same path |
| `skills/bmode/references/briefs/docs-review-finder.md` | Same path |
| `skills/bmode/references/briefs/docs-review-refuter.md` | Same path |
| `skills/bmode/references/briefs/fill-brief.py` | Same path |
| `skills/bmode/references/briefs/gen-issue-decider.md` | Same path |
| `skills/bmode/references/briefs/implementor.md` | Same path |
| `skills/bmode/references/briefs/reviewer.md` | Same path |
| `skills/bmode/references/briefs/scout.md` | Same path |
| `skills/bmode/references/briefs/shared-rules.md` | Same path |
| `skills/bmode/references/dispatch-loop.md` | Portable routing in `skills/bmode/SKILL.md` and `references/subagents.md`; original project rules archived |
| `skills/bmode/references/helpers.md` | Portable routing in `skills/bmode/SKILL.md` and `references/subagents.md`; original project rules archived |
| `skills/bmode/references/principles.md` | Portable routing in `skills/bmode/SKILL.md` and `references/subagents.md`; original project rules archived |
| `skills/bmode/references/repo-rules.md` | Portable routing in `skills/bmode/SKILL.md` and `references/subagents.md`; original project rules archived |
| `skills/bmode/references/subagents.md` | Same path |
| `skills/bmode/references/t3-model-routing.md` | Archived project or provider policy |
| `skills/bmode/references/triage.md` | Portable routing in `skills/bmode/SKILL.md` and `references/subagents.md`; original project rules archived |
| `skills/bmode/references/triggers.md` | Portable routing in `skills/bmode/SKILL.md` and `references/subagents.md`; original project rules archived |
| `skills/bmode/references/writing.md` | Portable routing in `skills/bmode/SKILL.md` and `references/subagents.md`; original project rules archived |
| `skills/bro/SKILL.md` | Same path |
| `skills/byte-handoff/SKILL.md` | Same path |
| `skills/correct/SKILL.md` | Same path |
| `skills/council-review/SKILL.md` | Same path |
| `skills/council-review/references/project-bphs-connect.md` | Archived project or provider policy |
| `skills/council-review/scripts/provider-usage.py` | Archived project or provider policy |
| `skills/docs-add/SKILL.md` | Same path |
| `skills/docs-review/SKILL.md` | Same path |
| `skills/figure-it-out/SKILL.md` | Same path |
| `skills/gen-issue/SKILL.md` | Same path |
| `skills/how/SKILL.md` | Same path |
| `skills/how/references/explainer-prompt.md` | Same path |
| `skills/how/references/explorer-prompt.md` | Same path |
| `skills/in-your-own-words/SKILL.md` | Same path |
| `skills/principle-attack-the-premise/SKILL.md` | Same path |
| `skills/principle-boundary-discipline/SKILL.md` | Same path |
| `skills/principle-build-the-lever/SKILL.md` | Same path |
| `skills/principle-encode-lessons-in-structure/SKILL.md` | Same path |
| `skills/principle-exhaust-the-design-space/SKILL.md` | Same path |
| `skills/principle-experience-first/SKILL.md` | Same path |
| `skills/principle-explain-the-number/SKILL.md` | Same path |
| `skills/principle-fix-root-causes/SKILL.md` | Same path |
| `skills/principle-foundational-thinking/SKILL.md` | Same path |
| `skills/principle-guard-the-context-window/SKILL.md` | Same path |
| `skills/principle-laziness-protocol/SKILL.md` | Same path |
| `skills/principle-make-operations-idempotent/SKILL.md` | Same path |
| `skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md` | Same path |
| `skills/principle-minimize-reader-load/SKILL.md` | Same path |
| `skills/principle-model-the-domain/SKILL.md` | Same path |
| `skills/principle-never-block-on-the-human/SKILL.md` | Same path |
| `skills/principle-outcome-oriented-execution/SKILL.md` | Same path |
| `skills/principle-prove-it-works/SKILL.md` | Same path |
| `skills/principle-redesign-from-first-principles/SKILL.md` | Same path |
| `skills/principle-separate-before-serializing-shared-state/SKILL.md` | Same path |
| `skills/principle-sequence-verifiable-units/SKILL.md` | Same path |
| `skills/principle-subtract-before-you-add/SKILL.md` | Same path |
| `skills/principle-test-behavior-not-implementation/SKILL.md` | Same path |
| `skills/principle-type-system-discipline/SKILL.md` | Same path |
| `skills/sharpen/SKILL.md` | Same path |
| `skills/sharpen/references/depth-audit.md` | Same path |
| `skills/sharpen/references/examples.md` | Same path |
| `skills/sharpen/references/leading-words.md` | Same path |
| `skills/sharpen/references/rules-matrix.md` | Same path |
| `skills/sol-loop/SKILL.md` | `skills/review-loop/SKILL.md` |
| `skills/swarm/SKILL.md` | Same path |
| `skills/technical-writing/SKILL.md` | Same path |
| `skills/typescript-best-practices/SKILL.md` | Same path |
| `skills/typescript-best-practices/references/patterns.md` | Same path |
| `skills/unslop/SKILL.md` | Same path |
