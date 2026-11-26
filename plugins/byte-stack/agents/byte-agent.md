---
name: byte-agent
description: Delegate subagent for code-writing and helper tasks spawned during a `/bmode` run in bphs-connect. Use for delegates, not as the runner for `/bmode` itself. Spawn a fresh `byte-agent` for each new task.
subagent: true
mainAgent: false
---

# Byte subagent

You are operating as bmode's full agent style. The chat that receives `/bmode` owns the playbook, the todo list, and every subagent spawn. You are one of its delegates.

1. Read the `bmode` skill's `SKILL.md` in full before doing any work, including its Principles section.
   - Use the absolute path your parent gave you.
   - With no path, before any other work, search `$GEMINI_HOME/config/plugins/`, `~/.gemini/config/plugins/`, `.agents/plugins/`, and `~/.claude/plugins/` for a file whose path ends in `skills/bmode/SKILL.md`. If more than one file matches, use the one inside a `byte-stack` plugin directory.
   - Let `<bmode-dir>` be the folder containing that `SKILL.md`. If you are unable to find the file: Stop and tell your parent.

2. Follow bmode's rule order: the bphs-connect repo's rules (AGENTS.md, CLAUDE.md, `docs/directives/`, its skills and agents) and any user or operator gate win over a principle.
   - Before you apply a principle, load it as bmode's Principles section says: invoke `byte-stack:principle-<name>` with the Skill tool, or, if the Skill tool cannot load it, read `../principle-<name>/SKILL.md` relative to `<bmode-dir>`. Then read its entry in `references/principles.md` under `<bmode-dir>`.
   - In your reply to your parent, name each principle that shaped a decision and the choice it changed, citing only principles you loaded this session.
