### Runtime forensics

**You own the diagnosis. Read the live process, do not theorize from source.** The deliverable is a cited diagnosis, not a fix.

Not established in bphs-connect: CPU profiles, heap snapshots, tracing, a logging library, or request IDs. The live signals are the server's `console` output, the `hono/logger` request lines, and the browser's console and page errors.

1. Pick the surface and find its log.
   - Local: `bun run dev` (the API on :3000; Vite prints the app address, `http://localhost:5173/` without Tailscale). Its log is the terminal it runs in.
   - Scratch: `docs/verify/scratch-server.sh start` (seeded, :3388, never the real `DATA_DIR`). Its log is `tmp/scratch-server/server.log`; `stop` deletes that folder, so read the log first.
   - Production (the VPS, from `/opt/bphs-connect`): work under `docs/directives/production-safety.md`. Never run a step with a `**Stop:**` line without the operator's go-ahead for that step in that session. Never use a real backup or a copy of the live database for development or tests. The app's log is Docker's: `sudo docker compose -f /etc/bphs-connect/compose.yml logs --tail 100 app` (add `-f` to follow; Docker keeps five files of 10 MB). `docs/how-to/troubleshoot.md` lists the first checks: the app's state and last error (`docs/how-to/run-project.md`, "Check the app"), the Nginx error log (`/var/log/nginx/error.log`), the backup log (`/var/log/bphs-backup.log`).
2. Redact every secret first: write `<REDACTED>` in its place. Quote only the lines that carry the signal. If the redacted output is not enough to diagnose, say so and ask the user.
3. Read what the process already logs:
   - The server has no logger. `console` is its log.
   - A start prints `Build <version>+<commit> · <n> migrations, … · maintenance webhook on|off`, then `BPHS-Connect listening on :<port> (<env>), data in <dir>`.
   - `hono/logger` prints two lines per request, `<--` as it arrives and `-->` with its status and time, unless the app is created with `quiet`.
   - An unexpected 5xx logs `<METHOD> <path> (<route>) failed, account <id or none>:` and the error (`app.onError` in `server/app.ts`).
   - A failed job logs `Job <name> failed:` and stops neither the other jobs nor the server.
   - A failing task-clock row logs `Task clock: task <id> failed` (or `series <id>`) the first time only, then stays failing and silent until a run where it does not fail (`modules/tasks/server/service.ts`).
   - A failed login logs a `console.warn`, with the user id and the attempt count when the account exists. It is not audited, except the attempt that locks the account.
   - The maintenance webhook warns on a refused entry and lists the keys received.
   - A bulk request logs its first 5xx fault in full, then one line for the failed rows (`bulkFaults` in `server/lib/errors.ts`).
   - In the browser, `node docs/verify/browser.mjs <address>` keeps a log of console and page errors for each page.
4. Map an error answer to its source with `docs/references/api-errors.md`: each status and code, with the file that throws it.
5. Prove the mechanism before believing it. First write 3 to 5 ranked, falsifiable hypotheses and show them to the user. Then add temporary logs tagged with a unique prefix such as `[DEBUG-a4f2]`, each mapped to one prediction, one variable at a time. Temporary production instrumentation needs the user's permission, and recreating the container is a `**Stop:**` step (`docs/how-to/run-project.md`, "Recreate the container"). Grep the prefix and remove every hit when done.
6. Map the finding to source: file, symbol, line. Name the first place the code went wrong, not the line that logged it (**principle-fix-root-causes**).

**Reply:** the signal captured, the reduced finding, how you proved the mechanism, the source location, and any artifact paths. No fix unless asked. Once the cause is known, hand back to Bug fix (`playbooks/bug-fix.md`) or Perf issue (`playbooks/perf-issue.md`).

Sources: .oxlintrc.json, server/app.ts, server/index.ts, server/services/auth.ts, modules/maintenance/server/webhook.ts, server/lib/errors.ts, docs/verify/browser.mjs, docs/verify/scratch-server.sh, docs/how-to/develop-locally.md, docs/directives/production-safety.md, docs/how-to/troubleshoot.md, docs/how-to/run-project.md, docs/references/production.md, docs/references/api-errors.md, modules/tasks/server/service.ts, server/startup.ts, .claude/skills/diagnosing-bugs/SKILL.md, AGENTS.md
