# Erosion vectors

Read this when reviewing a change for structural damage. Each vector lists what it looks like in a diff, how to confirm it, and the fitness function that would stop it next time.

Drift vs erosion (Perry & Wolf 1992): drift is a design choice that ignores the intended architecture without breaking a stated rule; erosion breaks a stated rule. Report erosion as a defect. Report drift as a Medium finding only when it adds a second way of doing something the codebase already does one way (conceptual integrity, Brooks 1975).

| Vector | Looks like in a diff | Confirm by | Principle | Fitness function |
|---|---|---|---|---|
| Boundary bypass | Import of another module's internal file instead of its public entry (`index.ts`, `__init__.py`, package API); visibility widened (`private` to `public`, `_name` used from outside, new `export` of an internal) | Open the target module: does it have a public entry that offers the same thing? | Information hiding (Parnas 1972) | import-linter, eslint-plugin-boundaries, dependency-cruiser, ArchUnit, Tach |
| Dependency cycle | New import from module A to B where B already reaches A | `coupling_metrics.py --compare` on base and head | Acyclic Dependencies Principle (Martin 2000) | madge --circular, dependency-cruiser no-circular, import-linter layers |
| Wrong direction | Domain/core imports framework, DB, HTTP, queue or LLM SDK; stable module imports less stable one | Read imports of touched core files; check I values | DIP, SDP (Martin 2000); ports and adapters (Cockburn 2005) | Layer contract in import-linter / ArchUnit |
| Clone-and-own | Same logic pasted in a new place; new helper that duplicates an existing one under another name | Search the repo for the core expression (`rg -n "<distinctive line>"`) and for synonyms of the function name | DRY (Hunt & Thomas 1999); Algorithm connascence | jscpd / PMD CPD with a duplication threshold |
| Complexity creep | Deep nesting, long functions, many branches added to an already complex function | Count branches; run lizard or radon if present | McCabe (1976) cyclomatic complexity; cognitive complexity (Campbell, SonarSource 2018) | lizard / radon / ESLint `complexity` with a cap |
| Hotspot growth | Change grows a file that already has high churn and high complexity, instead of splitting it | `diff_scan.py --repo` hotspots; file length | Hotspots = churn x complexity (Tornhill 2015) | CodeScene or code-maat report reviewed per sprint |
| Hidden co-change | Change touches a file that historically changes with another file, and the partner file is not in the diff | `diff_scan.py --repo` cochange_missing | Change coupling (Tornhill 2015/2024) | Co-change report; contract test between the pair |
| Contract break | Field removed or renamed, type narrowed, meaning changed, migration drops a column | Read schema and API diffs; check consumers | Expand and contract; tolerant reader | oasdiff breaking, Pact, migration linter (e.g. squawk for Postgres) |
| ADR violation | Change breaks an invariant in an Accepted ADR whose Scope matches the changed files | `adr_match.py` lists matching ADRs; read their Decision section | ADRs (Nygard 2011) | The ADR's own fitness function, if it has one; if not, propose one |

## Notes on judgement

- A boundary bypass inside one module (a file importing its sibling) is not a bypass. The boundary is the module's public entry as seen from outside.
- A cycle that already existed on the base branch is not a finding for this PR. Mention it only as context.
- Duplication of 3 to 5 trivial lines (guards, logging) is not clone-and-own. Duplication of a business rule is, even if it is 2 lines.
- Complexity added to a new, small, well-tested function is lower risk than the same added to a hotspot.
