#!/usr/bin/env python3
"""Module coupling metrics from a static import graph.

Computes, per module: Ca (afferent), Ce (efferent), I = Ce/(Ca+Ce)
(Martin 2000). Also finds dependency cycles (ADP) and Stable Dependencies
Principle violations (a module depending on a less stable one).

Supports TypeScript/JavaScript (.ts .tsx .mts .cts .js .jsx .mjs .cjs,
via regex) and Python (.py, via ast). Standard library only.

A "module" is, by default, a directory at --depth path components below
--root. Example: --root src --depth 1 makes src/billing/* one module
"billing". With --module, you name the modules instead (repeatable):
  --module 'modules/*'          each folder under modules/ is a module
  --module kernel=server        server/ is one module called "kernel"
A file under no --module pattern falls back to --depth.

Path aliases are read from <root>/package.json "imports" (#kernel/* ...)
and from tsconfig "paths" (root tsconfig.json and the projects it
references). Add more with --alias.

Usage:
  coupling_metrics.py --root src [--depth 1] [--alias @=src] [--json]
  coupling_metrics.py --root . --module 'modules/*' --module kernel=server --skip-tests
  coupling_metrics.py --root src --json > head.json
  coupling_metrics.py --root src --compare base.json   # what changed

Type-only imports (import type ..., export type ... from) are counted, and
edges made only of them are listed in "type_only_edges" (Connascence of
Type, which may cross a boundary). --runtime-only leaves them out.

Generated files (*.gen.ts, *.generated.ts, *_pb2.py) are left out by
default: a generated registry imports every module on purpose and would
hide real cycles. --keep-generated scans them; --exclude adds globs.

Limits: dynamic imports with computed paths, re-export chains through
packages outside --root, and languages other than Py/JS/TS are not seen.
Treat results as a floor, not the full truth.
"""
import argparse
import ast
import fnmatch
import json
import os
import re
import sys

SKIP_DIRS = {".git", "node_modules", "dist", "build", "out", ".venv", "venv",
             "__pycache__", ".next", ".turbo", "coverage", "vendor", ".tox",
             ".mypy_cache", ".pytest_cache", "target"}
PY_EXT = (".py",)
JS_EXT = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
JS_IMPORT = re.compile(
    r"""(?:\bimport\s+(type\s+)?(?:[\w*{}\s,$]+\s+from\s+)?|\bexport\s+(type\s+)?[\w*{}\s,$]*\s+from\s+|"""
    r"""\brequire\s*\(\s*|\bimport\s*\(\s*)['"]([^'"]+)['"]""")
GENERATED = re.compile(r"(\.gen\.[cm]?[jt]sx?$|\.generated\.[cm]?[jt]sx?$|_pb2\.py$)")
TEST_FILE = re.compile(r"(\.(test|spec)\.[cm]?[jt]sx?$|(^|/)(tests?|__tests__|testing)/|(^|/)test_[^/]*\.py$|_test\.py$)")


def strip_jsonc(text):
    """Remove // and /* */ comments and trailing commas (tsconfig is JSONC)."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def load_json(path, jsonc=False):
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        return json.loads(strip_jsonc(text) if jsonc else text)
    except (OSError, ValueError):
        return None


def auto_aliases(root):
    """Aliases from package.json "imports" and tsconfig "paths"."""
    found = []
    pkg = load_json(os.path.join(root, "package.json"))
    if isinstance(pkg, dict) and isinstance(pkg.get("imports"), dict):
        for k, v in pkg["imports"].items():
            if isinstance(v, str) and k.endswith("/*") and v.endswith("/*"):
                found.append((k[:-2], os.path.normpath(os.path.join(root, v[:-2]))))
    seen, queue = set(), [os.path.join(root, "tsconfig.json")]
    while queue:
        cfg = os.path.normpath(queue.pop())
        if cfg in seen:
            continue
        seen.add(cfg)
        if os.path.isdir(cfg):
            cfg = os.path.join(cfg, "tsconfig.json")
        data = load_json(cfg, jsonc=True)
        if not isinstance(data, dict):
            continue
        here = os.path.dirname(cfg)
        for ref in data.get("references", []) or []:
            if isinstance(ref, dict) and ref.get("path"):
                queue.append(os.path.join(here, ref["path"]))
        opts = data.get("compilerOptions", {}) or {}
        base = os.path.join(here, opts.get("baseUrl", "."))
        for k, vs in (opts.get("paths", {}) or {}).items():
            if k.endswith("/*") and vs and isinstance(vs[0], str) and vs[0].endswith("/*"):
                found.append((k[:-2], os.path.normpath(os.path.join(base, vs[0][:-2]))))
    out, keys = [], set()
    for k, v in found:
        if k not in keys:
            keys.add(k)
            out.append((k, v))
    return out


def walk(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith("."))
        for f in sorted(files):
            if f.endswith(PY_EXT + JS_EXT) and not f.endswith(".d.ts"):
                yield os.path.join(d, f)


def parse_patterns(raw):
    """'modules/*' or 'kernel=server' -> (label or None, [path parts], star)."""
    pats = []
    for x in raw:
        label, _, pat = x.rpartition("=")
        pat = pat.strip("/")
        star = pat.endswith("/*")
        parts = (pat[:-2] if star else pat).split("/")
        pats.append((label or None, parts, star))
    return pats


def module_of(path, root, depth, patterns=()):
    rel = os.path.relpath(path, root).split(os.sep)
    dirs = rel[:-1]
    for label, parts, star in patterns:
        if star:
            if len(dirs) > len(parts) and dirs[:len(parts)] == parts:
                name = "/".join(parts + [dirs[len(parts)]])
                return f"{label}:{dirs[len(parts)]}" if label else name
        elif rel[:len(parts)] == parts and len(rel) > len(parts):
            return label or "/".join(parts)
    if not dirs:
        return "(root)"
    return "/".join(dirs[:depth])


def py_index(files, root):
    """Map dotted module name -> file, for several plausible source roots."""
    idx = {}
    for f in files:
        if not f.endswith(".py"):
            continue
        rel = os.path.relpath(f, root)[:-3].split(os.sep)
        if rel[-1] == "__init__":
            rel = rel[:-1]
        for start in range(len(rel)):
            name = ".".join(rel[start:])
            if name:
                idx.setdefault(name, f)
    return idx


def py_imports(path, idx):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            tree = ast.parse(fh.read(), filename=path)
    except (SyntaxError, ValueError):
        return []
    pkg = os.path.dirname(path)
    out = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg
                for _ in range(node.level - 1):
                    base = os.path.dirname(base)
                cand = os.path.join(base, *(node.module or "").split(".")) if node.module else base
                for c in (cand + ".py", os.path.join(cand, "__init__.py")):
                    if os.path.isfile(c):
                        out.append(c)
                        break
                else:
                    for a in node.names:
                        c = os.path.join(cand, a.name + ".py")
                        if os.path.isfile(c):
                            out.append(c)
                continue
            mod = node.module or ""
            names = [mod + "." + a.name for a in node.names] + [mod]
        for n in names:
            parts = n.split(".")
            while parts:
                hit = idx.get(".".join(parts))
                if hit:
                    out.append(hit)
                    break
                parts.pop()
    return out


def js_resolve(spec, path, aliases):
    spec = spec.split("?")[0]
    for prefix, target in aliases:
        if spec == prefix or spec.startswith(prefix.rstrip("/") + "/"):
            spec = os.path.join(target, spec[len(prefix.rstrip("/")):].lstrip("/"))
            base = spec
            break
    else:
        if not spec.startswith("."):
            return None
        base = os.path.normpath(os.path.join(os.path.dirname(path), spec))
    stem = re.sub(r"\.(js|jsx|mjs|cjs)$", "", base)
    cands = [base] + [stem + e for e in JS_EXT] + [os.path.join(base, "index" + e) for e in JS_EXT]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def js_imports(path, aliases):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError:
        return []
    src = re.sub(r"(^|\s)/\*.*?\*/", r"\1", src, flags=re.S | re.M)
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    out = []
    for t1, t2, spec in JS_IMPORT.findall(src):
        r = js_resolve(spec, path, aliases)
        if r:
            out.append((r, bool(t1 or t2)))
    return out


def tarjan(nodes, edges):
    index, low, stack, on, sccs, n = {}, {}, [], set(), [], [0]
    sys.setrecursionlimit(max(10000, len(nodes) * 4))

    def visit(v):
        index[v] = low[v] = n[0]
        n[0] += 1
        stack.append(v)
        on.add(v)
        for w in sorted(edges.get(v, ())):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(sorted(comp))

    for v in sorted(nodes):
        if v not in index:
            visit(v)
    return sorted(sccs)


def analyse(root, depth, aliases, patterns=(), skip_tests=False, runtime_only=False,
            excludes=(), keep_generated=False):
    shown = root
    root = os.path.abspath(root)
    aliases = auto_aliases(root) + [(p, os.path.abspath(t)) for p, t in aliases]
    aliases.sort(key=lambda a: -len(a[0]))
    files, left_out = [], []
    for f in walk(root):
        rel = os.path.relpath(f, root).replace(os.sep, "/")
        if skip_tests and TEST_FILE.search(rel):
            continue
        if (not keep_generated and GENERATED.search(rel)) or any(fnmatch.fnmatch(rel, g) for g in excludes):
            left_out.append(rel)
            continue
        files.append(f)
    idx = py_index(files, root)
    edges, weight, type_w = {}, {}, {}
    nodes = set()
    for f in files:
        m = module_of(f, root, depth, patterns)
        nodes.add(m)
        if f.endswith(".py"):
            targets = [(t, False) for t in py_imports(f, idx)]
        else:
            targets = js_imports(f, aliases)
        per_target = {}
        for t, is_type in targets:
            per_target[t] = per_target.get(t, True) and is_type
        for t, is_type in per_target.items():
            if not t.startswith(root + os.sep):
                continue
            if is_type and runtime_only:
                continue
            tm = module_of(t, root, depth, patterns)
            nodes.add(tm)
            if tm != m:
                edges.setdefault(m, set()).add(tm)
                weight[(m, tm)] = weight.get((m, tm), 0) + 1
                if is_type:
                    type_w[(m, tm)] = type_w.get((m, tm), 0) + 1
    ca = {m: 0 for m in nodes}
    for m, ts in edges.items():
        for t in ts:
            ca[t] += 1
    metrics = {}
    for m in sorted(nodes):
        ce = len(edges.get(m, ()))
        i = round(ce / (ca[m] + ce), 2) if (ca[m] + ce) else None
        metrics[m] = {"Ca": ca[m], "Ce": ce, "I": i}
    sdp = []
    for m, ts in sorted(edges.items()):
        for t in sorted(ts):
            im, it = metrics[m]["I"], metrics[t]["I"]
            if im is not None and it is not None and im < it:
                sdp.append({"from": m, "to": t, "I_from": im, "I_to": it,
                            "imports": weight[(m, t)]})
    return {
        "root": shown,
        "depth": depth,
        "module_patterns": ["=".join(filter(None, [lbl, "/".join(p) + ("/*" if st else "")])) for lbl, p, st in patterns],
        "aliases": [[p, os.path.relpath(t, root)] for p, t in aliases],
        "tests_skipped": skip_tests,
        "excluded_files": left_out,
        "files_scanned": len(files),
        "modules": metrics,
        "edges": sorted([[a, b, weight[(a, b)]] for a in edges for b in edges[a]]),
        "type_only_edges": sorted([[a, b, weight[(a, b)]] for (a, b) in weight
                                   if type_w.get((a, b)) == weight[(a, b)]]),
        "cycles": tarjan(nodes, edges),
        "sdp_violations": sdp,
    }


def reaches(edges, src, dst):
    seen, stack = set(), [src]
    while stack:
        v = stack.pop()
        if v == dst:
            return True
        if v in seen:
            continue
        seen.add(v)
        stack.extend(edges.get(v, ()))
    return False


def _adj(edge_list):
    adj = {}
    for a, b, _ in edge_list:
        adj.setdefault(a, set()).add(b)
    return adj


def compare(base, head):
    be = {(a, b) for a, b, _ in base["edges"]}
    he = {(a, b) for a, b, _ in head["edges"]}
    bc = {tuple(c) for c in base["cycles"]}
    bs = {(v["from"], v["to"]) for v in base["sdp_violations"]}
    return {
        "new_edges": sorted([list(e) for e in he - be]),
        "removed_edges": sorted([list(e) for e in be - he]),
        "new_cycles": [c for c in head["cycles"] if tuple(c) not in bc],
        # A new edge a->b closes a cycle when b already reaches a. Read this
        # first: in a graph with one large cycle, "new_cycles" changes on any
        # membership change, while this names the edge that did it.
        "new_cycle_edges": [list(e) for e in sorted(he - be)
                            if reaches(_adj(head["edges"]), e[1], e[0])],
        "new_sdp_violations": [v for v in head["sdp_violations"] if (v["from"], v["to"]) not in bs],
        "instability_shift": {
            m: [base["modules"].get(m, {}).get("I"), v["I"]]
            for m, v in head["modules"].items()
            if base["modules"].get(m, {}).get("I") != v["I"]},
    }


def print_text(r):
    how = ", ".join(r["module_patterns"]) or f"module depth {r['depth']}"
    print(f"Scanned {r['files_scanned']} files under {r['root']} ({how})")
    if r["aliases"]:
        print("Aliases: " + ", ".join(f"{p} -> {t}" for p, t in r["aliases"]))
    print()
    print(f"{'module':40} {'Ca':>4} {'Ce':>4} {'I':>5}")
    for m, v in sorted(r["modules"].items(), key=lambda kv: (kv[1]["I"] is None, kv[1]["I"] or 0)):
        i = "-" if v["I"] is None else f"{v['I']:.2f}"
        print(f"{m:40} {v['Ca']:>4} {v['Ce']:>4} {i:>5}")
    print("\nCycles (ADP):", "none" if not r["cycles"] else "")
    for c in r["cycles"]:
        print("  " + " <-> ".join(c))
    print("\nSDP violations (depends on a less stable module):", "none" if not r["sdp_violations"] else "")
    for v in r["sdp_violations"]:
        print(f"  {v['from']} (I={v['I_from']}) -> {v['to']} (I={v['I_to']}), {v['imports']} import(s)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--module", action="append", default=[],
                    help="module pattern, repeatable: 'modules/*' or 'label=dir' (e.g. kernel=server)")
    ap.add_argument("--alias", action="append", default=[], help="extra JS path alias, e.g. @=src")
    ap.add_argument("--skip-tests", action="store_true", help="leave test files out")
    ap.add_argument("--runtime-only", action="store_true", help="leave type-only imports out")
    ap.add_argument("--exclude", action="append", default=[], help="glob of files to leave out, repeatable")
    ap.add_argument("--keep-generated", action="store_true",
                    help="scan *.gen.ts and other generated files (left out by default: they are composition roots)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--compare", help="earlier --json output to diff against")
    a = ap.parse_args()
    if not os.path.isdir(a.root):
        sys.exit(f"error: --root {a.root} is not a directory")
    aliases = [tuple(x.split("=", 1)) for x in a.alias if "=" in x]
    r = analyse(a.root, a.depth, aliases, parse_patterns(a.module), a.skip_tests, a.runtime_only,
                a.exclude, a.keep_generated)
    if a.compare:
        with open(a.compare, encoding="utf-8") as fh:
            print(json.dumps(compare(json.load(fh), r), indent=2))
    elif a.json:
        print(json.dumps(r, indent=2))
    else:
        print_text(r)


if __name__ == "__main__":
    main()
