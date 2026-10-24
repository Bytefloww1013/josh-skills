# TODO

## 1. Append-only event log (replaces handoff files)

- Keep an append-only content file that is written on any important event (decisions, completed slices, failed attempts, blockers, state changes).
- Goal: a fresh or compacted context can rebuild working state from this log, so handoff files are no longer needed.

## 2. CLI context management system

- Build a CLI that keeps context files out of the model's context window.
- Context is read through the CLI on demand (query/slice/summarize) rather than loaded wholesale.

## 3. BEADS in byte-gh-implement

- Incorporate BEADS into the `byte-gh-implement` skill.
- Take the GitHub issue and turn it into a BEADS database.
- Create a new BEADS db on each branch.
- Keep the grilling step and everything else in the skill as it is.
- Delete the old plan (the "only plane" in the original note, read as "old plan"; confirm if different).

## 4. Cleanup skill and docs skill

- Create a cleanup skill.
- Create a docs skill similar to `agent-context-kit`, but using my own conventions:
  - `/docs/how-to` - step-by-step procedural instructions for completing important tasks, one per file.
  - `/docs/directive` - conventions and standards, one per file, with a directory-wide `README`.
  - `/docs/scripts` - TBD (item was left unfinished in the original note).
