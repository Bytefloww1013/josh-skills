# Repository-owned Byte Stack assets

Accepted for the portability refactor. Claude Code is the primary target. Antigravity and Codex share the same skills with separate plugin manifests.

| Decision factor | Directory conventions | YAML register validated with JSON Schema |
| --- | --- | --- |
| Ownership | The plugin owns portable defaults. Each checkout owns its files. | Repo maintainers own assets and their registrations. |
| Discovery order | List one kind in stable key order. Resolve an exact key directly. | Parse and validate the register, then inspect each target. |
| Override precedence | The local key replaces the bundled asset in full. | A schema can describe aliases and ordered entries. A loader must detect conflicting registrations and missing targets. |
| Missing checkout assets | Missing key, kind or tree falls through to the bundle. Invalid overrides identify the broken path. | Missing and invalid registers require separate policies and diagnostics. |
| Dependencies | Git and the Python standard library. | A YAML parser, schema validator, schema version and path checks. |

Use the directory convention. Revisit registration when a real consumer needs aliases, conditional profiles or custom ordering. Initialize explicitly in the target worktree. A user-level install may serve many worktrees. The host discovers skills and Byte Stack discovers repository assets. Read the [resolution contract and example](../../plugins/byte-stack/README.md#add-a-repository-playbook).

Claude Code's Setup hook runs on explicit initialization and maintenance flags. Antigravity registers session and tool events. The skills installer can install individual skill directories. Codex supports user-invoked onboarding and discovers conventional plugin hooks unless the manifest overrides them. The package uses no repository-writing lifecycle hooks. [Claude hooks](https://code.claude.com/docs/en/hooks#setup) · [Antigravity hooks](https://antigravity.google/docs/hooks?tab=cli) · [Agent Skills](https://agentskills.io/specification) · [Codex plugin packaging](https://developers.openai.com/plugins/build/plugins)
