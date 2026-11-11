### Investigation

**You own the answer. Read only.** The deliverable is a cited explanation or a recommendation, not a code change.

1. For code, use CodeGraph before Read, Grep, Glob, find or an Explore agent, and trust its results (`CLAUDE.md`). Read Markdown, config, JSON and SQL migrations directly: CodeGraph does not index them. If the MCP tool is unavailable, run `codegraph explore "<query>"` in the shell. A SessionStart hook, `scripts/codegraph-ensure.sh`, builds or syncs the index. Do not run `codegraph init`. Where `codegraph` is not installed (a cloud session), there is no index, so use Read, Grep and Glob.
2. Start from the repo's own maps:
   - Architecture: `docs/references/architecture.md`, then `docs/references/modules.md` and the module's README.
   - Domain words: `docs/references/project-glossary.md`.
   - Past decisions: the ADRs in `docs/adr/`.
   - Rules for the whole repo: `docs/directives/` (`AGENTS.md`).
   - Scripts: `docs/references/commands.md`.
   - API errors: `docs/references/api-errors.md` gives each status and code with the file that throws it.
   - Other facts: `docs/references/` also holds `env-vars.md`, `production.md`, `refusals.md` and `security.md`.
   - What each doc is for: the doc index under `## Docs` in the root `README.md` (it also lists each module's README); `docs/README.md` says what each docs folder holds.
3. When the question is how a subsystem works, or where code should live and which module owns it, run the **how** helper, with the maps above as its grounding. When it is what a change could break, run the **blast-radius** helper. Its proof script goes under `tmp/`, so no repo file changes.
4. For a question that needs primary sources outside the code, such as library docs or specs, use the repo's `research` skill. It runs in a background agent and writes one Markdown file that cites each claim. The repo has no folder for such notes, so say where the file went. The skill is written for any repo, so it does not know this repo's glossary words or doc rules.
5. If the answer needs running data, use the seed or the scratch server (`docs/verify/scratch-server.sh start|stop`). Never use a real backup or the live or staging database (`docs/directives/production-safety.md`).
6. Cite every claim to a repo path and symbol. The repo's references cite file and symbol, never a line number (`docs/directives/writing-docs.md`), so keep line numbers out of anything that goes into a doc. For a choice between alternatives, give a recommendation with its tradeoffs. If the premise is wrong, say so with the evidence. Name a domain concept by the project glossary's word, never one in a term's `Not:` list. If the answer contradicts an ADR, say so (`docs/agents/domain.md`).
7. No branch, no PR. If the answer leads to a code change, hand back to the user and re-route to Bug fix (`playbooks/bug-fix.md`) or Feature (`playbooks/feature.md`).

**Reply:** the cited answer. For "are we sure?" questions, give your real judgment and the reasons for it.

#### Drift in the repo skills

- The `wait-what` skill cites `GLOSSARY-MAP.md`, and some skills read `GLOSSARY.md`. Neither exists. Use `docs/references/project-glossary.md`.
- `wait-what` sets `disable-model-invocation: true`. Only the user invokes it.

Sources: CLAUDE.md, AGENTS.md, README.md, docs/agents/domain.md, docs/directives/production-safety.md, docs/directives/writing-docs.md, docs/skills/research.md, docs/verify/scratch-server.sh, docs/references/architecture.md, docs/references/modules.md, docs/references/project-glossary.md, docs/adr/, docs/references/commands.md, docs/references/api-errors.md, docs/README.md, .claude/skills/research/SKILL.md, .claude/skills/wait-what/SKILL.md, .claude/skills/diagnosing-bugs/SKILL.md
