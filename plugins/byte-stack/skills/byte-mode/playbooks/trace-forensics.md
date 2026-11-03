### Trace forensics

**You own the diagnosis from the artifact.** The capture already exists. It is a fixed dataset: read it, do not re-run it. Runtime forensics (`playbooks/runtime-forensics.md`) instruments the live process instead.

Not established in bphs-connect: profiler or trace tooling, or a place or format for a handed-over artifact. Git-ignored `tmp/` holds only the `docs/verify` scripts' own scratch output (`tmp/browser`, `tmp/scratch-server`). The artifacts the `diagnosing-bugs` skill asks a user for are a redacted HAR file, log dump, core dump, or screen recording with timestamps.

1. Redact first. Captured artifacts carry auth headers. Write `<REDACTED>` for every secret, and quote only the lines that carry the signal.
2. Identify the format and load it with a tool that fits it. Parse a large artifact in a subagent and keep only the reduced finding in the main thread (**principle-guard-the-context-window**). Put derived output under `tmp/`, which git ignores. Never read staging's database or its pulled backups except through the staging script (`scripts/staging.sh`), and never copy them into the repo, `tmp/` or a test.
3. Narrow to the cause.
   - An HTTP error answer is JSON: `{ "error": <code>, "message": ..., "details"?: ... }`. Look up the status and code in `docs/references/api-errors.md`, which names the file that throws it.
   - A server log line maps to its source by its text. The known lines are listed in Runtime forensics step 3.
4. Attribute to source: file, symbol, line. A finding with no source location is not yet a diagnosis. Resolve it, or say plainly the artifact does not carry it and ask the user.
5. Confirm by replay where you can. The skill's "replay a captured trace" loop saves a real request, payload or event log to disk and replays it through the code path in isolation, for example as a Vitest test on the test kit's in-memory database. Without a replay or a paired capture, label the finding as the strongest hypothesis the artifact supports, not a confirmed cause, and state the prediction that would falsify it (skill Phase 3).
6. Hand back a cited diagnosis. No fix unless asked. Once the cause is known, route to Bug fix (`playbooks/bug-fix.md`) or Perf issue (`playbooks/perf-issue.md`).

**Reply:** the artifact and its format, the reduced finding, the source location, the artifact paths, and whether a replay or paired capture confirmed it.

Sources: .claude/skills/diagnosing-bugs/SKILL.md, .gitignore, docs/directives/production-safety.md, docs/references/api-errors.md, server/testing/index.ts, scripts/staging.sh, docs/verify/browser.mjs, docs/verify/scratch-server.sh
