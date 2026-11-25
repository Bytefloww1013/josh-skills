#!/usr/bin/env python3
"""Run diff_scan.py, scope_check.py and adr_match.py in one command.
Standard library only.

Writes `git diff <base>...HEAD` and the changed-file list to a temporary
directory (cleaned up on exit), runs the three sibling scans and prints their
outputs under `== diff_scan`, `== scope_check` and `== adr_match` headings
(or one combined JSON object with --json).

Exits non-zero only if git or a sub-script fails to run; scan findings are
information, not failures.

Usage:
  erosion_scan.py [--repo DIR] [--base main] [--branch NAME] [--issue N]... [--body FILE] [--adr-dir DIR] [--json]
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_ADR_DIRS = ("docs/adr", "docs/decisions", "doc/adr")


def run_cmd(cmd, cwd=None, text=True):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=text)
    except OSError as exc:
        return exc


def fail(step, result):
    if isinstance(result, OSError):
        sys.stderr.write(f"erosion_scan: {step} failed to start: {result}\n")
        sys.exit(1)
    detail = result.stderr.decode("utf-8", errors="replace") if isinstance(result.stderr, bytes) else result.stderr
    detail = detail.strip()
    msg = f"erosion_scan: {step} exited with status {result.returncode}"
    if detail:
        msg += f": {detail}"
    sys.stderr.write(msg + "\n")
    sys.exit(result.returncode or 1)


def current_branch(repo):
    res = run_cmd(["git", "-C", str(repo), "branch", "--show-current"])
    if isinstance(res, OSError) or res.returncode != 0:
        fail("git branch --show-current", res)
    return res.stdout.strip()


def resolve_dir_arg(repo, raw):
    if (repo / raw).is_dir():
        return raw
    p = Path(raw)
    if p.is_dir():
        return str(p.resolve())
    return raw


def find_adr_dirs(repo, explicit):
    if explicit:
        return [resolve_dir_arg(repo, d) for d in explicit]
    for candidate in DEFAULT_ADR_DIRS:
        if (repo / candidate).is_dir():
            return [candidate]
    return []


def run_sub(name, cmd, cwd=None, as_json=False):
    res = run_cmd(cmd, cwd=cwd)
    if isinstance(res, OSError) or res.returncode != 0:
        fail(name, res)
    out = res.stdout
    if as_json:
        try:
            return json.loads(out)
        except json.JSONDecodeError as exc:
            sys.stderr.write(f"erosion_scan: {name} returned invalid JSON: {exc}\n")
            sys.exit(1)
    return out.rstrip("\n")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="erosion_scan.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--repo", default=".", metavar="DIR", help="git repository root (default: cwd)")
    ap.add_argument("--base", default="main", metavar="REF", help="base ref for git diff <base>...HEAD (default: main)")
    ap.add_argument("--branch", default=None, metavar="NAME", help="head branch name (default: current branch)")
    ap.add_argument("--issue", action="append", default=[], metavar="N", help="known issue number (repeatable)")
    ap.add_argument("--body", default=None, metavar="FILE", help="file holding the PR body")
    ap.add_argument("--adr-dir", action="append", default=None, metavar="DIR",
                    help="ADR folder (repeatable; default: first existing of docs/adr, docs/decisions, doc/adr)")
    ap.add_argument("--rules-dir", action="append", default=[], metavar="DIR",
                    help="rule docs folder for adr_match.py (repeatable)")
    ap.add_argument("--area", action="append", default=[], metavar="PATTERN",
                    help="area pattern for diff_scan.py and scope_check.py (repeatable)")
    ap.add_argument("--json", action="store_true", help="output one combined JSON object")
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    repo = Path(a.repo).resolve()
    if not repo.is_dir():
        sys.stderr.write(f"erosion_scan: repo directory not found: {a.repo}\n")
        sys.exit(1)

    body_path = str(Path(a.body).resolve()) if a.body else None
    branch = a.branch if a.branch is not None else current_branch(repo)
    scripts_dir = Path(__file__).resolve().parent
    diff_range = f"{a.base}...HEAD"

    with tempfile.TemporaryDirectory(prefix="erosion-scan-") as tmp:
        tmp_dir = Path(tmp)
        diff_file = tmp_dir / "pr.diff"
        changed_file = tmp_dir / "changed.txt"

        diff_res = run_cmd(["git", "-C", str(repo), "diff", diff_range], text=False)
        if isinstance(diff_res, OSError) or diff_res.returncode != 0:
            fail(f"git diff {diff_range}", diff_res)
        diff_file.write_bytes(diff_res.stdout)

        names_res = run_cmd(["git", "-C", str(repo), "diff", "--name-only", diff_range], text=False)
        if isinstance(names_res, OSError) or names_res.returncode != 0:
            fail(f"git diff --name-only {diff_range}", names_res)
        changed_file.write_bytes(names_res.stdout)

        diff_cmd = [sys.executable, str(scripts_dir / "diff_scan.py"), str(diff_file), "--repo", str(repo)]
        for area in a.area:
            diff_cmd += ["--area", area]
        if a.json:
            diff_cmd.append("--json")

        scope_cmd = [sys.executable, str(scripts_dir / "scope_check.py"), str(changed_file), "--branch", branch]
        if body_path:
            scope_cmd += ["--body", body_path]
        for issue in a.issue:
            scope_cmd += ["--issue", issue]
        for area in a.area:
            scope_cmd += ["--area", area]
        if a.json:
            scope_cmd.append("--json")

        adr_dirs = find_adr_dirs(repo, a.adr_dir)
        rules_dirs = [resolve_dir_arg(repo, d) for d in a.rules_dir]

        diff_out = run_sub("diff_scan.py", diff_cmd, as_json=a.json)
        scope_out = run_sub("scope_check.py", scope_cmd, as_json=a.json)

        if adr_dirs or rules_dirs:
            adr_cmd = [sys.executable, str(scripts_dir / "adr_match.py"), str(changed_file)]
            for d in adr_dirs:
                adr_cmd += ["--adr-dir", d]
            for d in rules_dirs:
                adr_cmd += ["--rules-dir", d]
            if a.json:
                adr_cmd.append("--json")
            adr_out = run_sub("adr_match.py", adr_cmd, cwd=str(repo), as_json=a.json)
        else:
            note = f"no ADR folder found (checked {', '.join(DEFAULT_ADR_DIRS)})"
            adr_out = {"skipped": note, "matching": [], "without_scope": []} if a.json else f"skipped: {note}"

    if a.json:
        print(json.dumps({"diff_scan": diff_out, "scope_check": scope_out, "adr_match": adr_out}, indent=2))
    else:
        print("== diff_scan")
        print(diff_out)
        print("\n== scope_check")
        print(scope_out)
        print("\n== adr_match")
        print(adr_out)


if __name__ == "__main__":
    main()
