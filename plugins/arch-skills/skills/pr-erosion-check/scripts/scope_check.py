#!/usr/bin/env python3
"""Gather what a PR says it is for and what it actually touches, so the
reviewer can judge scope against the linked issue(s). Standard library only.

It does not judge. It finds:
  - linked issues: from the branch name (issue123, 123-fix-x, fix/123) and
    from closing keywords in the PR body (Closes #12, fixes owner/repo#12),
    plus other #N mentions;
  - the areas the change touches (same --area patterns as diff_scan.py),
    each with its files, split into code, tests, docs and incidental
    (lockfiles, generated files, migration snapshots);
  - the commands to read each linked issue.

Size is reported as information only. There is no size limit.

Usage:
  git diff --name-only origin/main...HEAD | scope_check.py - --branch "$(git branch --show-current)"
  scope_check.py changed.txt --branch feature/build-issue30-docs --body pr-body.md --area 'modules/*' --area 'foundation/*' --json
  gh pr view 41 --json body -q .body > body.md   # to get the body of an open PR
"""
import argparse
import json
import re
import sys

CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+((?:[\w.-]+/[\w.-]+)?#\d+)", re.I)
MENTION = re.compile(r"(?<![\w/])((?:[\w.-]+/[\w.-]+)?#\d+)\b")
BRANCH_ISSUE = [re.compile(r"issue[-_]?(\d+)", re.I), re.compile(r"(?:^|/)(\d+)(?:[-_]|$)"),
                re.compile(r"[-_/](?:gh|issue|iss)[-_]?(\d+)", re.I)]
INCIDENTAL = re.compile(r"(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?|poetry\.lock|uv\.lock|"
                        r"Cargo\.lock|go\.sum|\.gen\.[cm]?[jt]sx?$|\.generated\.|(^|/)migrations/meta/|"
                        r"\.snap$|CHANGELOG\.md$)")
TEST = re.compile(r"(^|/)(tests?|__tests__|spec|testing)/|\.(test|spec)\.[a-z]+$|_test\.(go|py)$|(^|/)test_[^/]+\.py$")
DOC = re.compile(r"\.(md|mdx|rst|txt)$|(^|/)docs?/")


def area_of(path, patterns):
    parts = path.split("/")
    for raw in patterns:
        label, _, pat = raw.rpartition("=")
        pat = pat.strip("/")
        star = pat.endswith("/*")
        pp = (pat[:-2] if star else pat).split("/")
        if star and len(parts) > len(pp) + 1 and parts[:len(pp)] == pp:
            return f"{label}:{parts[len(pp)]}" if label else "/".join(pp + [parts[len(pp)]])
        if not star and parts[:len(pp)] == pp and len(parts) > len(pp):
            return label or "/".join(pp)
    return parts[0] if len(parts) > 1 else "(root)"


def kind_of(path):
    if INCIDENTAL.search(path):
        return "incidental"
    if TEST.search(path):
        return "tests"
    if DOC.search(path):
        return "docs"
    return "code"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("changed", help="file with one changed path per line, or - for stdin")
    ap.add_argument("--branch", default="", help="head branch name")
    ap.add_argument("--body", help="file holding the PR body (or a draft of it)")
    ap.add_argument("--issue", action="append", default=[], help="an issue number the caller already knows")
    ap.add_argument("--area", action="append", default=[], help="area pattern, repeatable: 'modules/*' or 'label=dir'")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    src = sys.stdin if a.changed == "-" else open(a.changed, encoding="utf-8")
    changed = sorted({l.strip() for l in src if l.strip()})
    body = open(a.body, encoding="utf-8", errors="replace").read() if a.body else ""

    from_branch = []
    for rx in BRANCH_ISSUE:
        m = rx.search(a.branch)
        if m:
            from_branch.append("#" + m.group(1))
            break
    closing = sorted(set(CLOSING.findall(body)), key=lambda x: int(x.split("#")[1]))
    mentions = sorted(set(MENTION.findall(body)) - set(closing), key=lambda x: int(x.split("#")[1]))
    linked = []
    for x in from_branch + closing + ["#" + i.lstrip("#") for i in a.issue]:
        if x not in linked:
            linked.append(x)

    areas = {}
    for p in changed:
        k = kind_of(p)
        ar = "(incidental)" if k == "incidental" else area_of(p, a.area)
        areas.setdefault(ar, {"code": [], "tests": [], "docs": [], "incidental": []})[k].append(p)
    code_areas = sorted(x for x, v in areas.items() if v["code"])

    notes = []
    if not linked:
        notes.append("No linked issue found in the branch name or the PR body. Ask what the PR is for, "
                     "or judge scope from the PR title and description.")
    if len(linked) > 1:
        notes.append(f"{len(linked)} issues linked. Check that they are related (same feature, same module, "
                     "or one blocks the other). Unrelated issues in one PR is a scope finding.")
    if len(code_areas) > 1:
        notes.append(f"Code changes in {len(code_areas)} areas: {', '.join(code_areas)}. "
                     "For each area, find the sentence in the issue that needs it.")
    commands = [f"gh issue view {x.split('#')[1]}" + (f" -R {x.split('#')[0]}" if "/" in x else "")
                + " --json number,title,body,labels" for x in linked]
    out = {"branch": a.branch, "linked_issues": linked, "from_branch": from_branch, "closing_in_body": closing,
           "mentioned_in_body": mentions, "files": len(changed), "code_areas": code_areas, "areas": areas,
           "read_issues_with": commands, "notes": notes}
    if a.json:
        print(json.dumps(out, indent=2))
        return
    print(f"Branch: {a.branch or '(not given)'}")
    print(f"Linked issues: {', '.join(linked) or 'none'}"
          + (f"  (other mentions: {', '.join(mentions)})" if mentions else ""))
    print(f"{len(changed)} files; code in {len(code_areas)} area(s)\n")
    for ar in sorted(areas):
        v = areas[ar]
        counts = ", ".join(f"{k} {len(v[k])}" for k in ("code", "tests", "docs", "incidental") if v[k])
        print(f"  {ar}: {counts}")
        for p in (v["code"] + v["tests"] + v["docs"])[:6]:
            print(f"      {p}")
        extra = len(v["code"]) + len(v["tests"]) + len(v["docs"]) - 6
        if extra > 0:
            print(f"      ... and {extra} more")
    if commands:
        print("\nRead the issues:")
        for c in commands:
            print("  " + c)
    for n in notes:
        print("\nNote: " + n)


if __name__ == "__main__":
    main()
