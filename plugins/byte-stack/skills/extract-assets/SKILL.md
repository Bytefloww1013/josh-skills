---
name: extract-assets
description: Scan the current Git repository and propose repo-owned .byte-stack/ assets for explicit approval.
disable-model-invocation: true
argument-hint: "[--dry-run | category]"
---

# Extract Byte Stack assets

Scan the calling Git worktree and propose reusable repository-owned `.byte-stack/` assets (`playbooks/`, `workflows/`, `references/`, `scripts/`) with exact provenance and explicit user approval.

1. Locate the installed `bmode` skill directory (sibling `../bmode` in a full plugin install). If `bmode` is unavailable in a selective install, report that `bmode` is required and stop without writing `.byte-stack/` files.
2. From the target checkout, run the read-only inventory:
   `python3 "<extract-assets directory>/scripts/extract_assets.py" inventory`
   Review the returned JSON (classified files, bounded signals, bundled and repo `.byte-stack/` catalogs, exclusions, diagnostics). Read specific tracked files with bounded ranges or `rg` only when signals need clarification; never read secret, vendored, symlink, or machine-local files.
3. Resolve the synthesis guide (`python3 "<bmode directory>/scripts/assets.py" --owner "<extract-assets directory>" resolve references extract-assets.md`) and inspect the candidates schema (`python3 "<extract-assets directory>/scripts/extract_assets.py" schema`).
4. Synthesize a candidate JSON envelope covering workflows, conventions, rules, and other reusable knowledge. If the user passed a `category` (`workflow`, `convention`, `rule`, or `knowledge`), restrict synthesis to that category. Cite exact tracked provenance for every candidate and deduplicate against bundled `byte-stack`, existing `.byte-stack/`, and steering files.
5. Preview first with `--dry-run` (creates nothing on disk):
   `python3 "<extract-assets directory>/scripts/extract_assets.py" write --stdin --dry-run --json`
   Present each candidate's ID, category, provenance, dedupe verdict and reason, `similar_to` warnings, and unified diff. If the user passed `--dry-run`, stop here without writing; otherwise wait for explicit user approval of specific IDs (and explicit confirmation for any `--update`, `--override-bundled`, `--allow-duplicate`, or `--force` ID).
6. Write only approved IDs (`write --stdin --approve <id>...`), then report validation (`capture_playbook.py validate`) and discovery (`assets.py resolve`) results.
