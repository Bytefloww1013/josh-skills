### Install command:
```
npx skills add Bytefloww1013/josh-skills
```

### Plugins

`plugins/` holds Claude Code plugins, listed in `.claude-plugin/marketplace.json`. Install one with:

```
/plugin marketplace add Bytefloww1013/josh-skills
/plugin install byte-stack@josh-skills
```

To have a repo offer it to everyone who opens it, add to that repo's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "josh-skills": { "source": { "source": "github", "repo": "Bytefloww1013/josh-skills" } }
  },
  "enabledPlugins": { "byte-stack@josh-skills": true }
}
```

- **byte-stack** routes repository tasks through portable playbooks, engineering principles and review skills. Claude Code is the primary host. The same package includes Antigravity and Codex manifests. Run the init skill in a target checkout to add optional repository-owned assets. See [Byte Stack installation and usage](plugins/byte-stack/README.md).
- **arch-skills**: six architecture skills for agent-built code: `architecture-decision-review` (connascence and trade-offs before a design choice), `architecture-review-report` (evidence-based report on a plan, idea or issues), `pr-erosion-check` (scope against the linked issue, agent anti-patterns) `repo-navigability-audit`, `state-machine-audit` (implicit state machines, invalid states and a findings report) and `user-flow-mapper` (a user flow as Mermaid diagrams, then a prototype and UX report). Install with `/plugin install arch-skills@josh-skills` (or `agy plugin install plugins/arch-skills` for Antigravity). Its hook reminds you to run the PR check before `gh pr create` on both Claude Code and Antigravity and never blocks it. See `plugins/arch-skills/README.md`.

To verify Antigravity installation and hook behavior in an isolated `HOME` (requires `agy` on `PATH`; exits `2` when missing):

```
python3 tests/test_antigravity_plugin_install.py
```

### BPHS

`bphs/` holds BrightPath Human Services work skills, one folder per skill.

- **bphs-ingest-cc**: turns a Chase card workbook (Transactions + Accounts tabs) into a Chase Bank bill-import CSV for QuickBooks (Bill Numbers `CHS-#####`), one line per short-code and program 600-611.
