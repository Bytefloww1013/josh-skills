#!/usr/bin/env python3
"""List the ADRs and rule docs that govern the files a change touches.
Standard library only.

A doc's scope is read from either:
  - a "Scope:" line of path globs (the ADR template in these skills), or
  - a YAML front-matter "sources:" list (as in repos whose docs declare the
    files they describe, e.g. `sources: [server/modules.ts, web/src/**]`).

For each matching ADR it prints the Status, the decision text (the
"Decision" section, or the opening paragraphs when there is none), the
fitness functions, and what would reopen it. For each matching rule doc
(--rules-dir, e.g. docs/directives) it prints the rule bullets, split into
[judgment] rules (a reviewer must check them) and [enforced: ...] rules (a
script or linter checks them: do not re-report those, run the check).

Usage:
  git diff --name-only origin/main...HEAD | adr_match.py -
  git diff --name-only origin/main...HEAD | adr_match.py --adr-dir docs/adr --rules-dir docs/directives -
  adr_match.py changed.txt --json

Docs with no scope at all are listed by title; judge them by reading.
"""
import argparse
import fnmatch
import json
import os
import re
import sys

STATUS = re.compile(r"^\s*[-*]?\s*\**Status\**\s*:\s*\**\s*([A-Za-z ]+?)\b", re.I | re.M)
SCOPE = re.compile(r"^\s*[-*]?\s*\**Scope\**\s*:\s*(.+)$", re.I | re.M)
STATUS_HEAD = re.compile(r"^#+\s*Status\s*\n+\s*([A-Za-z]+)", re.I | re.M)
FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
RULE_TAG = re.compile(r"\[(judgment|enforced(?::[^\]]*)?)\]\s*$", re.I)


def front_list(front, key):
    """Read `key: [a, b]` or a `key:` followed by `- a` lines from front matter."""
    m = re.search(r"^" + key + r"\s*:\s*\[(.*?)\]", front, re.M | re.S)
    if m:
        return [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
    m = re.search(r"^" + key + r"\s*:\s*\n((?:\s*-\s*.+\n?)+)", front, re.M)
    if m:
        return [x.strip()[1:].strip().strip("'\"") for x in m.group(1).splitlines() if x.strip()]
    return []


def section(text, name):
    m = re.search(r"^#+\s*" + name + r"\b.*?\n(.*?)(?=^#+\s|\Z)", text, re.I | re.M | re.S)
    return m.group(1).strip() if m else ""


def opening(body):
    """Text after the title up to the first second-level heading."""
    lines = body.splitlines()
    start = next((i + 1 for i, l in enumerate(lines) if l.startswith("# ")), 0)
    out = []
    for l in lines[start:]:
        if l.startswith("## "):
            break
        out.append(l)
    return "\n".join(out).strip()


def glob_match(path, pat):
    pat = pat.strip().strip("`")
    if pat.endswith("/"):
        pat += "**"
    rx = (re.escape(pat).replace(r"\*\*/", "(.*/)?").replace(r"\*\*", ".*")
          .replace(r"\*", "[^/]*").replace(r"\?", "[^/]"))
    return re.fullmatch(rx, path) is not None or fnmatch.fnmatch(path, pat)


def rules_of(body):
    """Rule bullets with a [judgment] or [enforced: ...] tag at the end."""
    judged, enforced, cur = [], [], []

    def flush():
        if cur:
            text = " ".join(x.strip() for x in cur)
            m = RULE_TAG.search(text)
            if m:
                (judged if m.group(1).lower() == "judgment" else enforced).append(text)
    for line in body.splitlines():
        if re.match(r"^\s*[-*]\s+", line):
            flush()
            cur = [re.sub(r"^\s*[-*]\s+", "", line)]
        elif cur and line.startswith("  ") and line.strip():
            cur.append(line)
        else:
            flush()
            cur = []
    flush()
    return judged, enforced


def read_docs(folder, kind, changed):
    matches, unscoped = [], []
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".md") or f.lower() in ("readme.md", "index.md", "template.md"):
            continue
        path = os.path.join(folder, f)
        text = open(path, encoding="utf-8", errors="replace").read()
        fm = FRONT.match(text)
        front, body = (fm.group(1), text[fm.end():]) if fm else ("", text)
        title = next((l.lstrip("# ").strip() for l in body.splitlines() if l.startswith("#")), f)
        sm = STATUS.search(body) or STATUS_HEAD.search(body)
        status = sm.group(1).strip().title() if sm else ("Rule" if kind == "rule" else "Unknown")
        globs = []
        scm = SCOPE.search(body)
        if scm:
            globs = [g for g in re.split(r"[,\s]+", scm.group(1)) if g and g.lower() != "none"]
        globs += front_list(front, "sources")
        rec = {"file": os.path.join(folder, f), "kind": kind, "title": title, "status": status}
        if not globs:
            unscoped.append(rec)
            continue
        hit = sorted({p for p in changed for g in globs if glob_match(p, g)})
        if not hit:
            continue
        rec.update({"scope": globs, "matched_files": hit,
                    "enforced_by": front_list(front, "enforced-by")})
        if kind == "adr":
            rec["decision"] = (section(body, "Decision") or opening(body))[:1500]
            rec["fitness_functions"] = section(body, "Fitness functions")[:1000]
            rec["reopen_when"] = (section(body, "Revisit when") or section(body, "What would reopen it"))[:600]
        else:
            judged, enforced = rules_of(body)
            rec["judgment_rules"] = judged
            rec["enforced_rules"] = [r[:160] for r in enforced]
        matches.append(rec)
    return matches, unscoped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("changed", help="file with one changed path per line, or - for stdin")
    ap.add_argument("--adr-dir", action="append", help="ADR folder (repeatable). Default: docs/adr, docs/decisions, adr")
    ap.add_argument("--rules-dir", action="append", default=[],
                    help="folder of rule docs with sources: front matter, e.g. docs/directives (repeatable)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    adr_dirs = a.adr_dir or [d for d in ("docs/adr", "docs/decisions", "adr", "doc/adr") if os.path.isdir(d)]
    for d in (a.adr_dir or []) + a.rules_dir:
        if not os.path.isdir(d):
            sys.exit(f"no folder at {d}")
    if not adr_dirs and not a.rules_dir:
        sys.exit("no ADR folder found; pass --adr-dir (and --rules-dir for rule docs)")
    src = sys.stdin if a.changed == "-" else open(a.changed, encoding="utf-8")
    changed = [l.strip() for l in src if l.strip()]
    matches, unscoped = [], []
    for d in adr_dirs:
        m, u = read_docs(d, "adr", changed)
        matches += m
        unscoped += u
    for d in a.rules_dir:
        m, u = read_docs(d, "rule", changed)
        matches += m
        unscoped += u
    matches.sort(key=lambda r: (r["kind"] != "adr", r["status"] not in ("Accepted", "Rule"), r["file"]))
    out = {"changed_files": len(changed), "matching": matches, "without_scope": unscoped}
    if a.json:
        print(json.dumps(out, indent=2))
        return
    print(f"{len(changed)} changed files; {len(matches)} docs in scope; {len(unscoped)} docs without a scope")
    for r in matches:
        print(f"\n== {r['file']} [{r['status']}] {r['title']}\n   matches: {', '.join(r['matched_files'][:8])}")
        if r["kind"] == "adr":
            print("   Decision: " + (r["decision"].replace("\n", "\n   ") or "(none found)"))
            if r["fitness_functions"]:
                print("   Fitness functions: " + r["fitness_functions"].replace("\n", "\n   "))
            if r["reopen_when"]:
                print("   Reopen when: " + r["reopen_when"].replace("\n", "\n   "))
        else:
            if r["enforced_by"]:
                print("   Enforced by (run these, do not re-check by hand): " + ", ".join(r["enforced_by"]))
            for rule in r["judgment_rules"]:
                print("   [judgment] " + rule.replace(" [judgment]", ""))
            if r["enforced_rules"]:
                print(f"   ({len(r['enforced_rules'])} enforced rules omitted)")
    if unscoped:
        print("\nWithout scope (judge by title):")
        for r in unscoped:
            print(f"  {r['file']} [{r['status']}] {r['title']}")


if __name__ == "__main__":
    main()
