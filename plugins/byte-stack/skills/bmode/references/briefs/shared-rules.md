## Rules for every delegate

These rules win over anything else you read, except a gate the user or operator set.

1. **Run folder.** Write every scratch file, helper script, log and screenshot under `{{RUN_DIR}}`. In the checkout, write only what your role's rules allow.
2. **CodeGraph first.** {{CODEGRAPH_LINE}} It returns the line-numbered source, callers and blast radius, so trust it and read a file directly only for what it doesn't index (Markdown, JSON, SQL migrations) or a detail its output left out. Never run `codegraph init`, `index`, `sync` or `uninit`. Where the checkout has no `.codegraph/` folder or no `codegraph` command, search with `rg` instead.
3. **Script repeated work.** When a scan, count or check covers more than a few files, write a small script under `{{RUN_DIR}}`, run it, and give its command in your report.
4. **Stay inside the task.** Read only what `{{TASK_ID}}` needs: the files the task names, plus at most `{{READ_CAP}}` others. Summarise long command output and quote only its decisive lines. Command output here is condensed; treat it as complete, and rerun a command as `rtk proxy <cmd>` only when its result is empty, garbled or contradicts its exit code.
5. **Evidence for every claim.** Back each finding or result with:
   - the place: a repo-relative path, line range and symbol, written `server/access/route.ts:40-52` (`requires`);
   - a literal quote of 2 to 5 lines from the file;
   - for a command: the exact command, its exit code and its decisive output lines;
   - for something visual: a screenshot under `{{RUN_DIR}}` and one line on what it shows.
6. **Write for the next model.** The agent reading your report may be smaller than you. Name exact paths, symbols, signatures and invariants so it can act without searching again.
7. **Say what you don't know.** When a fact is missing or a check fails, record the gap or the error output word for word, and stop as your role's rules say. "Not found" is a valid answer.
8. **Repo rules.** `AGENTS.md` and `docs/directives/` in your checkout are the house rules, and `AGENTS.md` maps Claude tool names to yours. Never touch production, a backup or a real `DATA_DIR`; work on the seed. Push nothing, open or comment on no PR or issue, and start no subagents: the coordinator does all of that.
