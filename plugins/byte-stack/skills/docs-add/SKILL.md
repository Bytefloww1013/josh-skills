---
name: docs-add
description: Add a how-to, directive, reference or skill guide using the target repository's documentation conventions.
argument-hint: "how-to <topic> | directive <topic> | reference <topic> | skill <name> [--repo <owner/name>] [--install <command>]"
---

# Add a document

Resolve this skill's named assets from the target worktree. For example, for `references/KEY`, use `.byte-stack/references/docs-add/KEY` before the bundled `references/KEY`; use the same rule for workflows and scripts. With bmode installed, run `python3 "<bmode directory>/scripts/assets.py" --owner "<this skill directory>" resolve references KEY`. For a standalone install, use `git rev-parse --show-toplevel` and check the same paths with the host's file tools. Use the bundle outside Git. For a missing optional asset continue; report unreadable, empty or symlinked overrides. Accept only relative keys within the asset directory. Inspect scripts before authorized use.


Search existing docs, instructions and indexes for the topic. Extend an existing source when it already owns the answer. Read the nearest example of the requested type and the optional asset `references/criteria.md`.

- For a how-to, state prerequisites and ordered steps with an observable success condition. Mark irreversible actions and required approval.
- For a directive, give the rule, its scope and how it is enforced.
- For a reference, tie each fact to its owning file, symbol or specification.
- For a skill, explain installation, invocation, arguments, input and output. Use the supplied `--repo` or `--install` for an external skill when present. Verify the examples against the installed interface.

Write the document where the target repo keeps that type. Update the index using its existing generator or convention, then run the repo's documentation checks.
