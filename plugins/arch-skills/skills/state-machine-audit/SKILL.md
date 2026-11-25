---
name: "state-machine-audit"
description: "Find the implicit state machines in an app or repo, map them (Mermaid for big ones), judge whether each behavior is intended, flag paths to bugs or invalid states, and write a findings report."
---

# State machine audit

Read-only analysis. Never change the code under review.

## 1. Resolve the target

In this order:
1. An argument that is a local path: use it.
2. An argument that is a GitHub `owner/repo` or URL: `gh repo clone <repo> /tmp/sm-audit/<name> -- --depth 1`.
3. An argument that is an app name only: look for a matching repo (`gh repo list --limit 100 | grep -i <name>`); if more than one or none fits, ask.
4. No argument: `git rev-parse --show-toplevel` in the current directory.
5. Nothing found: ask for a path or repo.

Record the commit (`git rev-parse --short HEAD`) for the report.

## 2. Find candidates (scripted first, then read)

Run a candidate scan and save it to `/tmp/sm-audit/candidates.txt`:

```bash
rg -n --hidden -g '!node_modules' -g '!vendor' -g '!dist' -g '!*.lock' -i \
  -e '\b(status|state|phase|stage|step|mode|lifecycle)\b\s*[:=]' \
  -e '\benum\b' -e 'models\.TextChoices|IntegerChoices' \
  -e 'switch\s*\(.*(status|state|phase|step)' -e 'case\s+.*(STATUS|STATE)' \
  -e '\b(is|has)[A-Z][A-Za-z]*\s*[:=]\s*(true|false)' \
  -e '_(at|on)\b.*(null|None)' \
  -e 'useReducer|createMachine|transition|workflow|approve|reject|cancel|retry' \
  <repo> > /tmp/sm-audit/candidates.txt
```

Also check migrations/schema files for status columns, check constraints and defaults.

Implicit machines usually look like:
- a status/state/phase column or enum and the code that writes it
- clusters of booleans that together encode one state (`isLoading`, `isError`, `isDone`)
- nullable timestamps used as state (`signed_at`, `cancelled_at`, `deleted_at`)
- multi-step UI (wizards, approval flows, modals), reducers, retry/backoff loops
- background jobs, queues, webhooks, sync processes with started/finished markers

Group hits by entity. For a large repo, run one subagent per area (backend models, API, UI, jobs) in parallel, each returning machines in the format below; tell them not to post or edit anything.

## 3. Map each machine

For every machine record:
- **Entity and storage:** where the state lives (column, field, store).
- **States:** all values, plus initial and terminal states.
- **Transitions:** from, to, trigger, guard, and `file:line` of every write.
- **Enforcement:** DB constraint, central transition function, scattered guards, or none.
- **Derived/duplicate state:** other fields that must agree with it.

## 4. Analyse

Check each machine against this list:
- Writes that skip the guard or central function (state set directly from anywhere).
- Transitions allowed from terminal states (cancel after signed, edit after approved).
- Unreachable states and dead-end states with no way out.
- Impossible flag combinations that the code can still produce.
- Status and timestamps or derived fields that can disagree.
- Multi-write transitions without a transaction; partial failure leaves a mixed state.
- Races: read-check-write without locking or optimistic concurrency; double submit; retried jobs or webhooks that are not idempotent.
- UI and API enforcing different rules.
- Deactivated/deleted actors leaving work with no owner.
- Missing handling for an enum value (no default branch, unhandled case).

Judge intent from evidence: tests, docs, comments, ADRs, issues, commit messages. Rate each behaviour: **Intended**, **Likely intended**, **Unclear**, **Likely bug**, and give confidence (high/medium/low). Never call something a bug without the code path that reaches it.

## 5. Diagrams

- Use Mermaid `stateDiagram-v2` for any machine with more than 5 states, more than 7 transitions, or branching guards. Smaller ones get a transition table.
- Label edges with trigger and guard. Mark risky edges with a `note` and add a `classDef risky fill:#b00020,color:#ffffff` style; keep text high contrast.
- Keep each diagram one screen tall; split very large machines into sub-diagrams.

## 6. Report

Write `state-machine-report-YYYY-MM-DD.md` (outside the repo, or where the user says). Structure:

1. **Summary:** repo, commit, machines found, findings by severity.
2. **Inventory table:** machine, entity, states count, enforcement, risk rating.
3. **Per machine:** purpose, diagram or table, transition list with `file:line`, intent verdict.
4. **Findings:** ranked High/Medium/Low. Each has: what can go wrong, exact path to reach the invalid state (steps), evidence (`file:line`), intended or not, suggested fix, suggested test.
5. **Not checked / assumptions.**

Then give a short chat summary: count of machines, top 3 findings, report location. Offer to file GitHub issues for chosen findings; file nothing without a yes.