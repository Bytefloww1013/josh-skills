---
name: keep-context-lean
description: Use when a task will read many files, search a large codebase, look up documentation, or run long research or multi-step work, so the main conversation stays small. Also use when the conversation is past about 100k tokens.
---

# Keep the context lean

Every turn re-reads the whole conversation. File reads, skill bodies and long reasoning stay in it for the rest of the session.

- **Send big reads and searches to a subagent.** Ask it for a short answer with file:line references. Only that answer enters this conversation.
- **Read narrowly.** Search with Grep or Glob first, then read the line range you need. Don't read whole reference docs or large files.
- **Load a skill only for the step that needs it.** A loaded skill body stays in context for the session.
- **Keep reasoning proportionate.** Routine steps don't need long thinking, and thinking stays in context.
- **Checkpoint.** Past about 100k tokens, tell the user to run `/compact` at the next break. Tell them to run `/clear` before an unrelated task.
- **Keep mod and plugin development in its own session.** Each reload re-adds the skill list.
