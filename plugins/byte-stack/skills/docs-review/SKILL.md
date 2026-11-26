---
name: docs-review
description: Verify documentation claims against their owning code, refute unsupported findings and report actionable drift for a change or a full directory.
argument-hint: "pr [<PR number>] | full [<folder>] [--base <ref>] [--no-post]"
---

# Review docs

Resolve this skill's named assets from the target worktree. For example, for `references/KEY`, use `.byte-stack/references/docs-review/KEY` before the bundled `references/KEY`; use the same rule for workflows and scripts. With bmode installed, run `python3 "<bmode directory>/scripts/assets.py" --owner "<this skill directory>" resolve references KEY`. For a standalone install, use `git rev-parse --show-toplevel` and check the same paths with the host's file tools. Use the bundle outside Git. For a missing optional asset continue; report unreadable, empty or symlinked overrides. Accept only relative keys within the asset directory. Inspect scripts before authorized use.


1. For `pr`, identify the PR base and head or use the supplied `--base` and local change. Include docs affected by changed behavior. For `full`, inventory documentation under the selected folder or checkout. Check every claim against the same revision. Record exclusions.
2. Apply the optional asset `references/criteria.md` and the repo’s documented verification commands. Record any failed checks separately.
3. Collect each candidate mismatch with exact quotes and locations from the doc and its owning code. Verify both quotes at the reviewed revision. Give an independent refuter the quotes and locations without the finder’s rationale when authorized and available. Otherwise perform a second pass and disclose it. Drop findings refuted by another supported path.
4. Report scope, checked files, upheld findings, evidence and gaps. With posting authorized, publish the verified findings to the requested PR or tracker. Honor `--no-post` and omit empty reports from the tracker.
