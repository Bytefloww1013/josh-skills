# arch-skills

Four skills that help a coding agent keep a codebase sound. They share one library of principles (connascence, coupling metrics, erosion vectors, contracts, fitness functions, severity) and a project profile for bphs-connect.

| Skill | Use it when |
|---|---|
| `arch-skills:architecture-decision-review` | You must choose between design options before you build. Output: options, connascence table, decision, ADR. |
| `arch-skills:pr-erosion-check` | A PR or branch is ready for review, or an agent says it is done. Output: merge verdict with file:line findings, including scope against the linked issue. |
| `arch-skills:architecture-review-report` | You have a plan, spec, RFC or GitHub issues to review. Output: element-by-element report with severity and cited principle. |
| `arch-skills:repo-navigability-audit` | You want to know how easily an agent or a new person finds their way in a repo. Output: scored audit with fixes. |

Claude loads a skill by itself when the task fits its description. You can also call one by name, for example `/arch-skills:pr-erosion-check 41`.

## Install

```
claude plugin marketplace add Bytefloww1013/josh-skills
claude plugin install arch-skills@josh-skills
```

To try it without installing, from the josh-skills root: `claude --plugin-dir plugins/arch-skills`.

The scripts need Python 3 (standard library only). `pr-erosion-check` uses `git` and, for PRs, `gh`.

## The hook

`hooks/hooks.json` adds one PreToolUse hook. When Claude is about to run `gh pr create`, the hook adds a reminder to run `pr-erosion-check` first. It never blocks the command. To turn it off, delete `hooks/hooks.json`, or disable the plugin's hooks in your settings.

## Editing

Edit the skills here, in `skills/<name>/`. There is no build step.

Each skill carries its own copy of the reference files and scripts it shares with the others, so it works when installed alone. `severity.md`, `fitness-functions.md` and `project-bphs-connect.md` are in all four skills, and other files in two or three. When you change a shared file, change every copy, then run `plugins/arch-skills/check-copies.sh`. It names each file whose copies differ and exits 1 if any do.
