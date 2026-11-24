---
name: principle-guard-the-context-window
description: "Apply when context is filling up: large outputs, long files, repeated reads, fan-out planning. Route bulk to subagents; keep summaries in the main thread, not raw payloads."
---

# Guard the Context Window

Treat the context window as a budget. Spend the main thread's context on decisions, and send bulk reading somewhere that returns only what you need.

**Why:** Context overflow degrades reasoning quality, creates compression artifacts, and halts progress.

**Pattern:**
- **Size phases and cap scope.** Limit files per phase, set turn budgets, account for mechanism costs.
- **Route bulk to subagents.** A long log, a wide diff, a transcript, a trace, or a search across many files goes to a subagent whose brief asks for the reduced answer: the finding, the `file:line`, the count. Keep its summary, not its reads.
- **Use the cheapest tool that answers.** A code index query before a file read, a line range before the whole file, a count or a filtered search before a dump.
- **Don't reread.** Keep what you learned in a note or the todolist instead of opening the same file again.
- **Cap each subagent.** Give every brief a file and turn limit. A subagent with no cap spends tokens with nothing to show for it.
- **Hand off before overflow.** When the window nears its limit, write a handoff and continue fresh, rather than let compaction drop detail you needed.

**The test:** for each large block in your context, can you name the decision it fed? If not, it belonged in a subagent.

The human analog is [Minimize Reader Load](../principle-minimize-reader-load/SKILL.md): a reader's working memory is finite too.
