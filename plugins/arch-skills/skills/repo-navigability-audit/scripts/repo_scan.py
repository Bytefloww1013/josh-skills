#!/usr/bin/env python3
"""Mechanical navigability facts about a repository. Standard library only.

Collects the facts the audit scores; it does not score them.

Usage:
  repo_scan.py <repo-root> [--source-dirs src,packages,app] [--json]

Reports:
  front_doors     AGENTS.md / CLAUDE.md / ARCHITECTURE.md / README / CONTRIBUTING /
                  ADR folder / other agent rule files, with line counts
  nested_rules    AGENTS.md / CLAUDE.md files below the root (scoped memory)
  stale_links     paths named in front-door files that do not exist
  depth           max and distribution of directory depth for source files,
                  deepest paths
  generic_names   folders named utils, helpers, common, misc, shared, lib, core...
  wide_dirs       directories with very many direct source files
  modules         per top-level source module: has a public entry (index.*,
                  __init__.py, mod.rs, package.json, go package doc) or README
  exemplars       files or folders named example/template/golden/reference
  vocabulary      most frequent name tokens in folder and file names, and
                  candidate synonym pairs (for the ubiquitous-language check)
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

SKIP = {".git", "node_modules", "dist", "build", "out", ".venv", "venv", "__pycache__", ".next",
        "coverage", "vendor", "target", ".tox", ".idea", ".vscode", ".turbo", ".cache", "site-packages"}
SRC_EXT = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt", ".cs", ".rb",
           ".swift", ".php", ".scala", ".ex", ".exs", ".c", ".cc", ".cpp", ".h", ".hpp", ".vue", ".svelte")
FRONT = ["AGENTS.md", "CLAUDE.md", "ARCHITECTURE.md", "README.md", "CONTRIBUTING.md", "GEMINI.md",
         ".github/copilot-instructions.md", ".cursorrules", "CODEOWNERS", ".github/CODEOWNERS", "docs/README.md"]
ADR_DIRS = ["docs/adr", "doc/adr", "docs/adrs", "adr", "docs/decisions", "docs/architecture/decisions",
            "architecture/decisions", ".adr"]
RULE_DIRS = [".cursor/rules", ".claude/rules", ".github/instructions"]
GENERIC = {"utils", "util", "helpers", "helper", "common", "misc", "stuff", "general", "other", "tmp",
           "temp", "base", "shared", "lib", "libs", "core", "etc", "tools", "functions", "manager", "managers"}
STRONG_GENERIC = {"utils", "util", "helpers", "helper", "misc", "stuff", "general", "other", "etc"}
ENTRY = re.compile(r"^(index\.(ts|tsx|js|mjs)|__init__\.py|mod\.rs|lib\.rs|package\.json|doc\.go|"
                   r"README\.md|public[_-]?api\.\w+|api\.(ts|py))$")
EXEMPLAR = re.compile(r"(^|[-_.])(example|examples|exemplar|template|templates|golden|reference|sample|samples|"
                      r"_template|blueprint|scaffold)([-_.]|$)", re.I)
PATH_REF = re.compile(r"(?<![\w/.-])((?:\.{0,2}/)?(?:[\w.-]+/)+[\w.-]*|[\w-]+\.(?:md|py|ts|tsx|js|json|ya?ml|toml|go|rs))(?![\w/-])")
SYNONYMS = [("user", "account", "member", "customer", "client"), ("order", "purchase", "checkout"),
            ("item", "product", "sku", "article"), ("invoice", "bill", "statement"),
            ("payment", "charge", "transaction"), ("org", "organization", "tenant", "workspace", "company"),
            ("job", "task", "work", "worker"), ("event", "message", "notification"),
            ("auth", "authn", "login", "session", "identity"), ("config", "settings", "options", "prefs")]


def lines(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except OSError:
        return []


def tokens(name):
    name = re.sub(r"\.[a-z0-9]+$", "", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return [t.lower() for t in re.split(r"[^A-Za-z0-9]+", name) if len(t) > 2 and not t.isdigit()]


def scan(root, source_dirs):
    root = os.path.abspath(root)
    out = {"root": root}
    fd = {}
    for f in FRONT:
        p = os.path.join(root, f)
        if os.path.isfile(p):
            fd[f] = len(lines(p))
    docs = os.path.join(root, "docs")
    if os.path.isdir(docs):
        for d, dirs, files in os.walk(docs):
            if os.path.relpath(d, docs).count(os.sep) >= 2:
                dirs[:] = []
            for f in files:
                if f.lower() in ("architecture.md", "modules.md", "glossary.md", "conventions.md"):
                    rel = os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/")
                    fd.setdefault(rel, len(lines(os.path.join(d, f))))
    for d in ADR_DIRS:
        p = os.path.join(root, d)
        if os.path.isdir(p):
            fd[d + "/"] = len([x for x in os.listdir(p) if x.endswith(".md")])
    for d in RULE_DIRS:
        p = os.path.join(root, d)
        if os.path.isdir(p):
            fd[d + "/"] = len(os.listdir(p))
    out["front_doors"] = fd

    all_paths = set()
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP]
        rel = os.path.relpath(d, root).replace(os.sep, "/")
        if rel != ".":
            all_paths.add(rel)
        all_paths.update((f if rel == "." else rel + "/" + f) for f in files)

    def exists_anywhere(ref):
        """A path written relative to a module (shared/index.ts) counts if some repo path ends with it."""
        r = ref.strip("./").rstrip("/") if ref.startswith("./") else ref.rstrip("/")
        return r in all_paths or any(p.endswith("/" + r) for p in all_paths)

    stale = []
    for f in [x for x in fd if not x.endswith("/")]:
        if f in (".cursorrules", "CODEOWNERS", ".github/CODEOWNERS"):
            continue
        in_code = False
        for i, line in enumerate(lines(os.path.join(root, f)), 1):
            if line.strip().startswith("```"):
                in_code = not in_code
            for ref in PATH_REF.findall(line):
                ref = ref.rstrip(".,:;)")
                if "://" in line and ("http" in ref or "." in ref.split("/")[0]):
                    continue
                if ref.count("/") == 0 and not ref.endswith(".md"):
                    continue
                last = ref.rstrip("/").split("/")[-1]
                if ref.startswith("/") or ("." not in last and not ref.endswith("/")):
                    continue  # absolute paths and prose like PASS/FAIL or rule names
                cand = os.path.normpath(os.path.join(root, ref.lstrip("./") if ref.startswith("./") else ref))
                if "*" in ref or "<" in ref or ref.startswith("~"):
                    continue
                if (not os.path.exists(cand) and not os.path.exists(os.path.join(root, os.path.dirname(f), ref))
                        and not exists_anywhere(ref)):
                    stale.append({"file": f, "line": i, "ref": ref})
    out["stale_links"] = stale[:50]

    depth_count = Counter()
    deepest = []
    generic = []
    wide = []
    nested_rules = []
    exemplars = []
    name_tok = Counter()
    dirs_seen = 0
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP and not (x.startswith(".") and x not in (".github", ".claude", ".cursor")))
        rel = os.path.relpath(d, root)
        parts = [] if rel == "." else rel.split(os.sep)
        dirs_seen += 1
        for x in parts[-1:]:
            name_tok.update(tokens(x))
            if x.lower() in GENERIC:
                srcs = sum(1 for f in files if f.endswith(SRC_EXT))
                generic.append({"dir": rel, "strong": x.lower() in STRONG_GENERIC, "source_files": srcs})
            if EXEMPLAR.search(x):
                exemplars.append(rel + "/")
        if parts and ("AGENTS.md" in files or "CLAUDE.md" in files):
            nested_rules += [os.path.join(rel, f) for f in ("AGENTS.md", "CLAUDE.md") if f in files]
        srcs = [f for f in files if f.endswith(SRC_EXT)]
        if len(srcs) >= 25:
            wide.append({"dir": rel, "source_files": len(srcs)})
        for f in srcs:
            depth_count[len(parts)] += 1
            name_tok.update(tokens(f))
            deepest.append((len(parts), os.path.join(rel, f)))
            if EXEMPLAR.search(f):
                exemplars.append(os.path.join(rel, f))
    deepest.sort(key=lambda x: -x[0])
    total = sum(depth_count.values())
    out["depth"] = {
        "source_files": total,
        "max": max(depth_count) if depth_count else 0,
        "histogram": dict(sorted(depth_count.items())),
        "share_deeper_than_4": round(sum(v for k, v in depth_count.items() if k > 4) / total, 2) if total else 0,
        "deepest": [p for _, p in deepest[:10]],
    }
    # A generic name repeated under 3+ sibling modules (modules/*/shared) is a
    # layout convention, not a dumping ground: report it once as a convention.
    groups = {}
    for g in generic:
        parts = g["dir"].split(os.sep)
        key = (os.sep.join(parts[:-2]), parts[-1]) if len(parts) >= 3 else None
        groups.setdefault(key, []).append(g)
    folded = []
    for key, gs in groups.items():
        if key and len(gs) >= 3:
            folded.append({"dir": os.path.join(key[0], "*", key[1]), "convention": True, "count": len(gs),
                           "strong": gs[0]["strong"], "source_files": sum(x["source_files"] for x in gs)})
        else:
            folded += gs
    out["generic_names"] = sorted(folded, key=lambda g: g["dir"])
    out["wide_dirs"] = sorted(wide, key=lambda x: -x["source_files"])[:15]
    out["nested_rules"] = nested_rules
    out["exemplars"] = exemplars[:20]

    mods = []
    for sd in source_dirs:
        base = os.path.join(root, sd)
        if not os.path.isdir(base):
            continue
        for m in sorted(os.listdir(base)):
            mp = os.path.join(base, m)
            if not os.path.isdir(mp) or m in SKIP or m.startswith("."):
                continue
            entries = [f for f in os.listdir(mp) if ENTRY.match(f)]
            # one side folder down (server/index.ts, web/index.ts, ...)
            for side in sorted(os.listdir(mp)):
                sp = os.path.join(mp, side)
                if os.path.isdir(sp) and side not in SKIP and not side.startswith("."):
                    entries += [side + "/" + f for f in os.listdir(sp) if ENTRY.match(f) and f != "README.md"]
            nsrc = sum(1 for _, _, fs in os.walk(mp) for f in fs if f.endswith(SRC_EXT))
            if nsrc:
                mods.append({"module": os.path.join(sd, m), "source_files": nsrc, "entry_files": entries})
    out["modules"] = mods

    syn = []
    for group in SYNONYMS:
        present = {w: name_tok[w] + name_tok[w + "s"] for w in group if name_tok[w] + name_tok[w + "s"]}
        if len(present) > 1:
            syn.append(present)
    out["vocabulary"] = {"top_tokens": name_tok.most_common(30), "possible_synonyms": syn}
    out["dirs_scanned"] = dirs_seen
    return out


def guess_source_dirs(root):
    found = [d for d in ("src", "app", "apps", "packages", "lib", "services", "internal", "pkg", "cmd", "modules", "features", "foundation")
             if os.path.isdir(os.path.join(root, d))]
    return found or ["."]


def print_text(r):
    print(f"Repo: {r['root']}  ({r['dirs_scanned']} dirs)\n")
    print("Front doors:", r["front_doors"] or "NONE")
    print("Nested agent rule files:", r["nested_rules"] or "none")
    print(f"Stale paths in front doors: {len(r['stale_links'])}")
    for s in r["stale_links"][:15]:
        print(f"  {s['file']}:{s['line']} -> {s['ref']}")
    d = r["depth"]
    print(f"\nDepth: {d['source_files']} source files, max depth {d['max']}, "
          f"{int(d['share_deeper_than_4'] * 100)}% deeper than 4; histogram {d['histogram']}")
    for p in d["deepest"][:5]:
        print("  deep:", p)
    print("\nGeneric folder names:", "none" if not r["generic_names"] else "")
    for g in r["generic_names"]:
        conv = f", convention in {g['count']} modules" if g.get("convention") else ""
        print(f"  {g['dir']} ({g['source_files']} source files{conv}){' [strong]' if g['strong'] else ''}")
    print("\nWide directories (>=25 source files):", "none" if not r["wide_dirs"] else "")
    for w in r["wide_dirs"]:
        print(f"  {w['dir']}: {w['source_files']}")
    print("\nModules and public entry points:")
    for m in r["modules"]:
        print(f"  {m['module']:40} files={m['source_files']:<4} entry={m['entry_files'] or 'NONE'}")
    print("\nExemplars:", r["exemplars"] or "none found by name")
    print("\nTop name tokens:", ", ".join(f"{t}({n})" for t, n in r["vocabulary"]["top_tokens"][:20]))
    print("Possible synonym clusters:", r["vocabulary"]["possible_synonyms"] or "none")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--source-dirs", help="comma list; default: guess (src, app, packages, ...)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(a.root):
        sys.exit(f"error: {a.root} is not a directory")
    sds = a.source_dirs.split(",") if a.source_dirs else guess_source_dirs(a.root)
    r = scan(a.root, sds)
    r["source_dirs"] = sds
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print_text(r)


if __name__ == "__main__":
    main()
