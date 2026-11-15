# Information architecture for repositories

Read this when judging how easily a person or an agent can find, understand and extend code in a repository.

## Contents
- Brown's eight principles, applied to repos
- The four-layer disclosure topology
- Ubiquitous language
- Conway and ownership
- Scoring rubric (0 to 2 per check)

## Brown's eight principles, applied to repos

Dan Brown, "Eight Principles of Information Architecture", *Bulletin of the American Society for Information Science and Technology* 36(6), 2010. The mapping to repositories is our application, not Brown's.

| Principle | In a repository | Evidence to collect |
|---|---|---|
| Objects | Each domain concept has one name, one owner and a clear lifecycle across DB, API, code and docs | Synonym clusters in names (`repo_scan.py` vocabulary); same concept with different names in schema vs code |
| Choices | Few, meaningful extension points; no pile of near-duplicate helpers or dozens of flags | Count of config flags, near-duplicate helpers, parallel ways to do one thing |
| Disclosure | Read order is short summary, then public interfaces, then internals | Front-door files exist and are short; modules have public entries |
| Exemplars | One golden-path example of a feature and of a test that newcomers can copy | Named exemplar or one clearly pointed to from AGENTS.md |
| Front doors | Every subsystem has one obvious entry: router, CLI command, worker entry, package API | Entry files per module; AGENTS.md says where to start |
| Multiple classification | Code can be found by business capability and by technical role | Feature folders plus tags/CODEOWNERS/OpenAPI/dependency graph |
| Focused navigation | Shallow, specific folders; no `utils/helpers/common/misc` chains | Depth histogram; generic names; wide directories |
| Growth | Adding module 50 follows the same pattern as module 5 | A template, generator or documented recipe; modules look alike |

## The four-layer disclosure topology

| Layer | Contents | Good looks like |
|---|---|---|
| 1. Front doors | AGENTS.md (or CLAUDE.md), ARCHITECTURE.md, docs/adr/ | Root AGENTS.md is short and points elsewhere; ARCHITECTURE.md names modules, boundaries and dependency rules (Aleksey Kladov, "ARCHITECTURE.md", 2021: a short map of the code, kept current); ADRs exist for Type 1 decisions |
| 2. Taxonomy | Top-level feature or module folders | 3 to 4 levels from root to most source files; names are domain words |
| 3. Contracts | Public entry per module (`index.ts`, `__init__.py` with `__all__`, package API), schemas | Outsiders import only the entry |
| 4. Internals | Handlers, queries, tests | Read only when needed; exemplar shows the pattern |

Front-door content guidance (AGENTS.md, see agents.md): build and test commands, where things live, conventions that differ from defaults, things not to touch and why (with ADR links). Keep it short and specific; long generic files waste every session's context. Nested AGENTS.md files in subfolders hold rules for that subtree only; the nearest file wins. Every path named in a front door must exist (`repo_scan.py` stale_links).

What the evidence says about front doors (read it before scoring):
- Gloaguen et al. (arXiv 2602.11988, 2026) tested context files on coding benchmarks. Files written by an LLM slightly lowered task success and raised cost by about a fifth; files written by developers did better than generated ones. Repository overviews did not help agents reach the relevant file sooner, but agents did follow specific instructions (for example, which tool to run). Their advice: include only specific instructions the code itself does not show.
- Lulla et al. (arXiv 2601.20404, 2026) found AGENTS.md associated with lower agent runtime and token use on real PRs (correlational).
- HumanLayer ("Writing a good CLAUDE.md"): keep it well under 300 lines, only content relevant to every task, point to files instead of copying them, do not use it for style rules a linter can enforce, do not auto-generate it.
- Kladov ("ARCHITECTURE.md", 2021): a short codemap of coarse modules; name important files and types instead of linking them (links go stale; symbol search does not); state invariants, especially absences ("the model does not depend on the views"); mark boundaries; list cross-cutting concerns.

So score front doors on content: specific, hand-written, short, current. A long or generated overview scores 1 at best, however complete it looks. The find-the-code test, not the presence of a file, is the evidence for Disclosure and Front doors.

## Ubiquitous language

Evans, *Domain-Driven Design* (2003): one model, one vocabulary, used in code, schema, API and talk, within a bounded context. Check: pick the 5 to 10 most frequent domain nouns; for each, list every name used for it across folders, types, tables and endpoints. More than one name per concept inside one bounded context is a finding. Different names in different bounded contexts can be correct; say which context each belongs to.

## Conway and ownership

Conway (1968): system structure mirrors communication structure. For agents: assign owners (people and agent scopes) to module boundaries, not to layers. Evidence: CODEOWNERS aligned with module folders; parallel agent tasks given disjoint folders. Shared mutable files that every feature edits (one giant routes file, one registry, one constants file) are merge-conflict and erosion points.

## Scoring rubric (0 to 2 per check)

| Score | Meaning |
|---|---|
| 2 | Present and good; evidence cited |
| 1 | Present but weak, stale or partial |
| 0 | Missing or actively harmful |

Score each of Brown's eight principles plus the four topology layers (12 checks, 24 points). Report the score with the evidence, never the score alone. Rank fixes by (impact on finding things) / (effort), not by score order.
