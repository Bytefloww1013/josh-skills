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

- **byte-stack**: `bmode` for bphs-connect, its playbooks, the principle skills it applies, its helper skills (`how`, `architect`, `arena`, `ketchup` and more), and the `byte-agent` delegate subagent. Most skills are manual-only (`disable-model-invocation: true`); run them as `/byte-stack:<skill>`. `how`, `blast-radius`, `unslop` and `technical-writing` are also model-invoked, so Claude can start them when a request fits, and `bmode`'s playbooks run the helpers each step names.
