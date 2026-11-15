#!/usr/bin/env python3
"""Mechanical erosion signals from a unified diff. Standard library only.

Each signal is a CANDIDATE for the reviewer to confirm by reading the hunk.
The script never decides severity; SKILL.md does.

Usage:
  git diff origin/main...HEAD > pr.diff
  diff_scan.py pr.diff [--repo .] [--since "6 months ago"] [--area 'modules/*'] [--json]
  git diff main...HEAD | diff_scan.py - --repo .

Signals:
  size          lines changed (lockfiles/generated excluded), files, areas.
                Information only: size is never a finding by itself. Use
                scope_check.py to compare the areas with the linked issue.
  tests         assertion delta in test files, skip/only markers, loose matchers,
                deleted test files, mocks added
  swallow       empty or value-returning catch/except, `|| true`, `_ = err`
  suppress      lint/type suppressions added (noqa, ts-ignore, eslint-disable...)
  bypass        imports into internal/private paths, deep relative imports
  abstraction   new Factory/Registry/Strategy/Base/interface/ABC declarations,
                with repo-wide reference counts when --repo is given
  clones        identical 6-line blocks repeated inside the added code
  nesting       added lines at deep indentation (complexity creep proxy)
  hotspots      (--repo) churn of touched files over --since
  cochange      (--repo) files that usually change with touched files but are
                missing from this diff (temporal coupling, Tornhill)
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

GENERATED = re.compile(r"(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Pipfile\.lock|"
                       r"go\.sum|Cargo\.lock|composer\.lock|Gemfile\.lock|\.min\.(js|css)$|\.snap$|"
                       r"\.map$|(^|/)(dist|build|vendor|generated|__generated__)/|\.pb\.go$|_pb2\.py$|"
                       r"\.gen\.[cm]?[jt]sx?$|\.generated\.[cm]?[jt]sx?$|(^|/)migrations/meta/[^/]+\.json$)")
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|specs)/|\.(test|spec)\.[a-z]+$|_test\.(go|py|rb)$|"
                       r"(^|/)test_[^/]+\.py$|(^|/)[A-Z]\w*Tests?\.(java|kt|cs)$")
ASSERT = re.compile(r"\bassert\w*\b|\bexpect\s*\(|\.should\b|\bt\.(Error|Errorf|Fatal|Fatalf|Fail)\b|"
                    r"\brequire\.\w+\(|\bXCTAssert\w*|\bpytest\.raises\b|\bself\.fail\b|\bverify\s*\(")
SKIP_MARK = re.compile(r"\.(skip|only)\s*\(|\bx(it|describe|test)\s*\(|@pytest\.mark\.(skip|xfail)|"
                       r"@unittest\.skip|\bpytest\.skip\(|@Disabled\b|@Ignore\b|\bt\.Skip\(|\[Ignore\]|#\[ignore\]")
LOOSE = re.compile(r"expect\.anything\(|expect\.any\(|\.toBeTruthy\(|\.toBeDefined\(|\bmock\.ANY\b|"
                   r"\bassert\s+True\b|assertTrue\(\s*True|\.toMatchObject\(|\.toBeCloseTo\(|"
                   r"assertIsNotNone\(|\.not\.toThrow\(")
MOCK = re.compile(r"\bjest\.mock\(|\bvi\.mock\(|\bsinon\.(stub|mock)\(|\bMagicMock\(|\bMock\(|"
                  r"@patch\b|\bpatch\(|\bmocker\.patch|\bgomock\.|\bMockito\.")
SUPPRESS = re.compile(r"#\s*noqa|#\s*type:\s*ignore|@ts-ignore|@ts-expect-error|@ts-nocheck|"
                      r"eslint-disable|//\s*nolint|@SuppressWarnings|#\[allow\(|pylint:\s*disable|"
                      r"istanbul ignore|pragma:\s*no cover|NOSONAR|rubocop:disable")
TODO = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
CATCH_INLINE = re.compile(r"catch\s*(\([^)]*\))?\s*\{\s*\}|\.catch\(\s*\(?[^)]*\)?\s*=>\s*(\{\s*\}|null|undefined|\[\]|\{\}|false)\s*\)|"
                          r"\bexcept\s*:\s*pass\b|\bexcept\s+(Exception|BaseException)\b[^:]*:\s*(pass|return\b.*|continue)\s*$|"
                          r"\|\|\s*true\s*$|^\s*_\s*=\s*err\b|rescue\s*=>\s*\w+\s*$|rescue\s+nil")
CATCH_OPEN = re.compile(r"\bcatch\s*(\([^)]*\))?\s*\{\s*$|\bexcept\s*(\w[\w.]*)?(\s+as\s+\w+)?\s*:\s*$|\bexcept\s*\(([^)]*)\)\s*(as\s+\w+)?\s*:\s*$")
SWALLOW_BODY = re.compile(r"^\s*(\}|pass|continue|return(\s+(null|None|undefined|nil|false|False|\[\]|\{\}|\"\"|''|0|-1))?\s*;?)\s*$")
BROAD = re.compile(r"\bexcept\s*:|\bexcept\s+(Exception|BaseException)\b|\bexcept\s*\(.*\bException\b|catch\s*\(\s*(e|err|error|ex|_)?\s*(:\s*(any|unknown|Exception|Throwable|Error))?\s*\)|catch\s*\{")
IMPORT_LINE = re.compile(r"^\s*(import\b|from\s+\S+\s+import\b|export\s+.*\bfrom\b|.*\brequire\s*\(|use\s+\w)")
BYPASS = re.compile(r"""['"/.](internal|_internal|private|_private|impl)(['"/.]|$)|\.\./\.\./\.\./""")
ABSTRACT = re.compile(r"\b(?:abstract\s+class|class|interface|trait|protocol|type)\s+"
                      r"([A-Z]\w*(?:Factory|Registry|Provider|Strategy|Manager|Builder|Handler|Plugin|Base|Abstract\w*)|"
                      r"I[A-Z]\w+|Abstract\w+|Base[A-Z]\w*)\b|"
                      r"\bclass\s+([A-Z]\w*)\s*\(\s*(?:ABC|Protocol|abc\.ABC|Generic\[.*\])\s*\)|"
                      r"\binterface\s+([A-Z]\w*)")


def parse_diff(text):
    files, cur, new_ln = [], None, 0
    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", raw)
            cur = {"path": m.group(2) if m else raw, "added": [], "removed": [], "deleted": False, "new": False}
            files.append(cur)
        elif cur is None:
            continue
        elif raw.startswith("deleted file mode"):
            cur["deleted"] = True
        elif raw.startswith("new file mode"):
            cur["new"] = True
        elif raw.startswith("+++ ") or raw.startswith("--- "):
            if raw.startswith("+++ b/"):
                cur["path"] = raw[6:]
        elif raw.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", raw)
            new_ln = int(m.group(1)) if m else 0
        elif raw.startswith("+"):
            cur["added"].append((new_ln, raw[1:]))
            new_ln += 1
        elif raw.startswith("-"):
            cur["removed"].append(raw[1:])
        elif raw.startswith(" "):
            new_ln += 1
    return files


def git(repo, *args):
    try:
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return ""


def history(repo, since, max_files=50):
    """List of commits (sets of paths), skipping bulk commits."""
    out = git(repo, "log", f"--since={since}", "--no-merges", "--format=format:@@C", "--name-only")
    commits, cur = [], set()
    for line in out.splitlines():
        if line == "@@C":
            if cur and len(cur) <= max_files:
                commits.append(cur)
            cur = set()
        elif line.strip():
            cur.add(line.strip())
    if cur and len(cur) <= max_files:
        commits.append(cur)
    return commits


def count_refs(repo, names):
    if not names:
        return {}
    pats = {n: re.compile(r"\b" + re.escape(n) + r"\b") for n in names}
    counts = Counter()
    for d, dirs, fs in os.walk(repo):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in {"node_modules", "dist", "build", "vendor", ".venv"}]
        for f in fs:
            if not f.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".kt", ".cs", ".rb", ".rs", ".swift", ".php")):
                continue
            try:
                src = open(os.path.join(d, f), encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for n, p in pats.items():
                counts[n] += len(p.findall(src))
    return dict(counts)


def indent_unit(lines):
    widths = [len(l) - len(l.lstrip(" ")) for _, l in lines if l.strip() and not l.startswith("\t")]
    nz = sorted({w for w in widths if w})
    return nz[0] if nz and nz[0] in (2, 4) else 4


def area_of(path, patterns):
    """First matching --area pattern ('modules/*' or 'label=dir'), else the top-level folder."""
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


def scan(files, repo=None, since="6 months ago", nest_limit=5, areas=()):
    s = defaultdict(list)
    size = {"files": 0, "added": 0, "removed": 0, "areas": Counter(), "test_added": 0, "src_added": 0}
    added_src_lines = []
    for f in files:
        p = f["path"]
        if GENERATED.search(p):
            continue
        is_test = bool(TEST_PATH.search(p))
        size["files"] += 1
        size["added"] += len(f["added"])
        size["removed"] += len(f["removed"])
        size["areas"][area_of(p, areas)] += 1
        size["test_added" if is_test else "src_added"] += len(f["added"])
        if is_test:
            a_add = sum(1 for _, l in f["added"] if ASSERT.search(l))
            a_rem = sum(1 for l in f["removed"] if ASSERT.search(l))
            if f["deleted"]:
                s["tests"].append({"file": p, "kind": "test file deleted", "assertions_removed": a_rem})
            elif a_rem > a_add:
                s["tests"].append({"file": p, "kind": "assertion count fell", "removed": a_rem, "added": a_add})
            for ln, l in f["added"]:
                if SKIP_MARK.search(l):
                    s["tests"].append({"file": p, "line": ln, "kind": "skip/only marker added", "code": l.strip()})
                if LOOSE.search(l):
                    s["tests"].append({"file": p, "line": ln, "kind": "loose matcher added", "code": l.strip()})
                if MOCK.search(l):
                    s["tests"].append({"file": p, "line": ln, "kind": "mock added (check it is not the unit under test)", "code": l.strip()})
        added = f["added"]
        unit = indent_unit(added)
        deepest = None
        for i, (ln, l) in enumerate(added):
            st = l.strip()
            if not is_test:
                if CATCH_INLINE.search(l):
                    s["swallow"].append({"file": p, "line": ln, "code": st})
                elif CATCH_OPEN.search(l):
                    nxt = [x for _, x in added[i + 1:i + 3] if x.strip() and not x.strip().startswith(("//", "#"))]
                    if nxt and SWALLOW_BODY.match(nxt[0]):
                        s["swallow"].append({"file": p, "line": ln, "code": st + " ... " + nxt[0].strip()})
                    elif BROAD.search(l):
                        s["swallow"].append({"file": p, "line": ln, "code": st, "note": "broad catch; check it re-raises or logs with context"})
                if ABSTRACT.search(l):
                    m = ABSTRACT.search(l)
                    name = next(g for g in m.groups() if g)
                    s["abstraction"].append({"file": p, "line": ln, "name": name})
                lead = len(l) - len(l.lstrip(" \t"))
                lvl = l[:lead].count("\t") + (lead - l[:lead].count("\t")) // unit
                if st and lvl >= nest_limit and (deepest is None or lvl > deepest[1]):
                    deepest = (ln, lvl)
            if SUPPRESS.search(l):
                s["suppress"].append({"file": p, "line": ln, "code": st})
            if TODO.search(l):
                s["todo"].append({"file": p, "line": ln, "code": st})
            if IMPORT_LINE.search(l) and BYPASS.search(l):
                s["bypass"].append({"file": p, "line": ln, "code": st})
        if deepest:
            s["nesting"].append({"file": p, "line": deepest[0], "indent_levels": deepest[1]})
        if not is_test:
            added_src_lines += [(p, ln, re.sub(r"\s+", " ", l.strip())) for ln, l in added]

    # clones inside the added code: 6 consecutive meaningful lines seen twice
    seen, clones = {}, []
    meaningful = [x for x in added_src_lines if len(x[2]) > 3 and x[2] not in ("}", "{", ")", "]", "});", "end")]
    for i in range(len(meaningful) - 5):
        block = meaningful[i:i + 6]
        if len({b[0] for b in block}) > 1:
            continue
        h = hashlib.sha1("\n".join(b[2] for b in block).encode()).hexdigest()
        if h in seen and seen[h][0] != (block[0][0], block[0][1]):
            clones.append({"first": f"{seen[h][0][0]}:{seen[h][0][1]}", "again": f"{block[0][0]}:{block[0][1]}"})
        else:
            seen.setdefault(h, ((block[0][0], block[0][1]),))
    s["clones"] = clones[:20]

    changed = size["added"] + size["removed"]
    result = {"size": {**size, "areas": dict(size["areas"]), "changed_lines": changed},
              "signals": {k: v for k, v in s.items() if v}}

    if repo:
        touched = {f["path"] for f in files}
        commits = history(repo, since)
        churn = Counter(p for c in commits for p in c if p in touched)
        result["hotspots"] = [{"file": p, "commits": n} for p, n in churn.most_common(10)]
        co = defaultdict(Counter)
        for c in commits:
            for p in c & touched:
                for q in c - {p}:
                    co[p][q] += 1
        missing = []
        for p in sorted(touched):
            n = churn.get(p, 0)
            for q, k in co[p].most_common(5):
                if q not in touched and n >= 4 and k >= 3 and k / n >= 0.5 and os.path.exists(os.path.join(repo, q)):
                    missing.append({"touched": p, "usually_changes_with": q, "together": k, "of": n})
        result["cochange_missing"] = missing
        names = sorted({a["name"] for a in s.get("abstraction", [])})
        refs = count_refs(repo, names)
        for a in s.get("abstraction", []):
            a["repo_references"] = refs.get(a["name"], 0)
    return result


def print_text(r):
    z = r["size"]
    print(f"Size (information only): {z['files']} files, +{z['added']} -{z['removed']} "
          f"({z['changed_lines']} changed); src +{z['src_added']}, tests +{z['test_added']}; areas: {z['areas']}")
    for k, items in r["signals"].items():
        print(f"\n[{k}] {len(items)}")
        for it in items[:25]:
            loc = f"{it.get('file', '')}:{it['line']}" if "line" in it else it.get("file", "")
            rest = {x: y for x, y in it.items() if x not in ("file", "line")}
            print(f"  {loc} {rest}" if loc else f"  {rest}")
    for k in ("hotspots", "cochange_missing"):
        if r.get(k):
            print(f"\n[{k}]")
            for it in r[k]:
                print(f"  {it}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("diff", help="unified diff file, or - for stdin")
    ap.add_argument("--repo", help="repo root, enables hotspots, co-change and reference counts")
    ap.add_argument("--since", default="6 months ago")
    ap.add_argument("--area", action="append", default=[],
                    help="how to group files into areas, repeatable: 'modules/*' or 'label=dir'")
    ap.add_argument("--nest-limit", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    text = sys.stdin.read() if a.diff == "-" else open(a.diff, encoding="utf-8", errors="replace").read()
    r = scan(parse_diff(text), a.repo, a.since, a.nest_limit, a.area)
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print_text(r)


if __name__ == "__main__":
    main()
