---
name: repo-navigability-audit
description: Audits how easily people and coding agents find, understand and extend code in a repo, and returns a scored report with ranked fixes and an AGENTS.md draft. Use to audit a repo's structure, make it agent-ready, or set up AGENTS.md or CLAUDE.md.
---

# Repo Navigability Audit

Measure how fast a newcomer (a person or an agent with no memory) can get from "I have a task" to "these are the files to change", then fix what slows them down.

## The core rule

Score nothing without evidence, and test with real tasks. A repo can tick every box (it has an AGENTS.md, it has folders) and still be hard to navigate. The find-the-code test in Step 4 is what shows it.

Why: agents and newcomers fail in the same way. When they cannot find the existing code, they write a second copy. That is where duplication and boundary bypasses start.

## Step 0. Repo first

If the repo has `app.modules.ts` and `docs/verify/gate-checks.txt`, read `references/project-bphs-connect.md` first: it names the module layout and the conventions (such as `<module>/shared/`) that are deliberate, so you do not score them as clutter.

## Step 1. Scope

- Single repo: audit from the root.
- Monorepo: audit the root front doors, then each package the user names (or the 3 most active: `git log --since="3 months ago" --format= --name-only | cut -d/ -f1-2 | sort | uniq -c | sort -rn | head`).
- Ask nothing if the scope is clear from the request. Do not move, rename or delete files during the audit.

## Step 2. Scan

```
python3 scripts/repo_scan.py <repo-root>            # add --source-dirs src/features,packages if the guess is wrong
python3 scripts/repo_scan.py <repo-root> --json     # for exact numbers
```

Run it with `--help` the first time. It reports front doors, nested rule files, stale paths in front doors, depth, generic folder names, wide folders, public entries per module, exemplars, and name tokens with possible synonym clusters. It collects facts; it does not score.

## Step 3. Read the front doors

Read in full: root AGENTS.md or CLAUDE.md, ARCHITECTURE.md, README.md, and the ADR index or the 5 newest ADRs. For each, note:
- Does it say where to start, how to build and test, and what not to touch (with reasons)?
- Is it specific to this repo (conventions that differ from defaults, invariants, commands), or generic advice the model already knows?
- Was it written by a person? Generated overviews tend to restate the README and the folder tree; research found they add cost without helping agents find files.
- Is it short (well under 300 lines), and does it point to files instead of copying them?
- Does it hold style rules a linter should enforce? Those belong in the linter.
- Does every path it names exist? (`stale_links` in the scan)

Then read `references/information-architecture.md` for the principles and the scoring rubric.

## Step 4. Find-the-code test

This is the most important step. It is tree testing (an established IA method) applied to a repo.

1. Pick 3 real tasks. Take them from recent commit or PR titles (`git log --oneline -30`), open issues, or ask the user. Mix: one feature addition, one bug fix, one cross-cutting change.
2. For each task, start from the front doors only and find the files you would change. Use only what a new agent would use: reading files, listing folders, text search.
3. Record for each task: steps taken (files opened plus searches), where you went wrong, the files you ended at, and whether the git history for that real change touched the same files.
4. A task that took more than about 8 steps, or ended in the wrong place, is evidence for a finding. Name the exact missing signpost.

If the repo has no history, say so and use tasks the user gives you. Keep the tasks and step counts in the report: after the fixes land, the same test run again is the before-and-after measure.

## Step 5. Check the vocabulary

If the repo has a glossary (GLOSSARY.md, a Glossary section in ARCHITECTURE.md, or a domain docs page), check names against it. Otherwise, from `vocabulary` in the scan and from the domain types you read, pick the 5 to 10 main domain nouns. For each, list every name used for it across folders, types, tables and API routes. More than one name for one concept inside one bounded context is a finding (Evans 2003). Different names in different bounded contexts may be correct: say which context each belongs to.

## Step 6. Score

Score the 12 checks in the rubric (Brown's eight principles plus the four layers), 0 to 2 each, with one line of evidence per score. Use `references/severity.md` for findings.

## Step 7. Plan the fixes

Rank fixes by how much they shorten the find-the-code test, divided by effort. Typical high-value fixes, cheapest first:

1. Fix stale paths in front doors.
2. Write or cut down the root AGENTS.md (template: `assets/AGENTS.template.md`).
3. Write ARCHITECTURE.md as a short map of modules and dependency rules (template: `assets/ARCHITECTURE.template.md`).
4. Add a public entry to each module that lacks one, and point outsiders to it.
5. Name one golden-path example of a feature and of a test, and link both from AGENTS.md.
6. Add nested AGENTS.md files only where a subtree has rules that differ from the root.
7. Rename or dissolve generic folders (`utils/`, `helpers/`, `common/`, `misc/`): move each file next to its only caller, or into a named domain module. This is a plan, not an action; it needs the owner's yes.
8. Add fitness functions: a CI check for stale front-door paths, a depth or forbidden-folder-name lint, CODEOWNERS per module (`references/fitness-functions.md`).

Offer to write the drafts for items 1 to 3. Make no moves or renames without the user's yes.

## Step 8. Output

```
REPO NAVIGABILITY AUDIT: <repo> (<scope>)
Score: <n>/24    Find-the-code: <tasks passed>/<tasks run>, median <n> steps
Verdict: <one sentence: the single biggest obstacle>

Top fixes (ranked):
  1. <fix> | effort: S/M/L | evidence: <short> | expected effect: <which test task gets shorter>
  2. ...

Find-the-code results:
  T1 "<task>": <steps> steps, <found right files: yes/no>, lost at: <where>
  ...

Scores:
| Check | Score | Evidence |
| Objects (one name per concept) | 1 | invoice/bill used for the same thing in src/billing and api/routes |
| ... 12 rows ... |

Findings: (severity, confidence, evidence, principle, fix), Critical to Low, then Positive
Vocabulary: <concept: names found, and where>
Drafts offered: <AGENTS.md / ARCHITECTURE.md / none>
Not checked: <what and why>
```

## Red flags: stop and correct yourself

| If you think... | Do this instead |
|---|---|
| "AGENTS.md exists, so front doors score 2." | Read it. Score its content: specific, short, current, correct paths. |
| "A longer AGENTS.md is better." | Every line is read in every session. Cut generic advice; link to details instead. |
| "I'll generate a full AGENTS.md overview from the tree." | Write only what the code does not already show: commands, unusual conventions, invariants, where to start. |
| "Deep folders are bad, so flatten everything." | Depth is a problem when it makes search fail. Use the find-the-code results, not the number alone. |
| "`shared/` is a generic name, so it is a finding." | Check what is in it. A small, owned kernel of domain types is fine; a dumping ground is not. |
| "I'll reorganise the folders to show what good looks like." | Propose a move plan. Never move files during an audit. |
| "The scan is the audit." | The scan gives facts. Steps 3 to 5 are the audit. |

## Gotchas

- Do not penalise framework conventions (Next.js `app/`, Rails `app/models`, Django apps). Judge against the framework's own norms first.
- A monorepo package with its own README and entry point counts as a front door for that package.
- `repo_scan.py` guesses source folders (`src`, `app`, `packages`, ...). If modules live one level lower (`src/features/*`), rerun with `--source-dirs`.
- Stale-link detection matches path-like text; a few hits may be examples in prose, paths written through an import alias (`kernel/http.ts` for `server/http.ts`), or files git ignores on purpose. Check before reporting.
- A generic folder name repeated under every module (`modules/*/shared`) is a layout convention. The scan folds it into one line; judge it as a convention, not as a dumping ground.
