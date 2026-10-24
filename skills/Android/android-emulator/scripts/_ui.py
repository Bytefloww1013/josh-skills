#!/usr/bin/env python3
"""UI-hierarchy helper used by emu-ui-list.sh / emu-tap-text.sh.

  _ui.py list <dump.xml> [--all]
  _ui.py find <dump.xml> <query> [--exact] [--index N]
      -> prints "x y<TAB>description" for the chosen node, exit 1 if none.
Matching order (first non-empty tier wins):
  1 exact text  2 exact content-desc  3 exact resource-id (full or after ':id/')
  4 case-insensitive substring of text/content-desc (skipped with --exact)
Within a tier: visible nodes first, then clickable ones, then document order.
"""
import re, sys
import xml.etree.ElementTree as ET

B = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

def nodes(path):
    for n in ET.parse(path).iter("node"):
        m = B.match(n.get("bounds", ""))
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        yield {
            "text": n.get("text", ""), "desc": n.get("content-desc", ""),
            "id": n.get("resource-id", ""), "cls": n.get("class", "").rsplit(".", 1)[-1],
            "clickable": n.get("clickable") == "true", "enabled": n.get("enabled") == "true",
            "pkg": n.get("package", ""), "bounds": (x1, y1, x2, y2),
            "visible": x2 > x1 and y2 > y1, "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
        }

def label(n):
    parts = []
    if n["text"]: parts.append(f'text="{n["text"]}"')
    if n["desc"]: parts.append(f'desc="{n["desc"]}"')
    if n["id"]: parts.append(f'id={n["id"]}')
    parts.append(n["cls"])
    if n["clickable"]: parts.append("clickable")
    return " ".join(parts)

def cmd_list(path, show_all):
    for n in nodes(path):
        if not n["visible"]:
            continue
        if show_all or n["text"] or n["desc"] or n["clickable"]:
            print(f'{n["cx"]:>4},{n["cy"]:<5} {label(n)}')

def cmd_find(path, q, exact, index):
    ns = [n for n in nodes(path) if n["visible"]]
    ql = q.lower()
    short = lambda rid: rid.split(":id/", 1)[-1]
    tiers = [
        [n for n in ns if n["text"] == q],
        [n for n in ns if n["desc"] == q],
        [n for n in ns if n["id"] and (n["id"] == q or short(n["id"]) == q)],
    ]
    if not exact:
        tiers.append([n for n in ns if ql and (ql in n["text"].lower() or ql in n["desc"].lower())])
    for t in tiers:
        if t:
            t = sorted(t, key=lambda n: (not n["clickable"],))  # stable: clickable first
            if index >= len(t):
                print(f"only {len(t)} match(es) for {q!r}", file=sys.stderr)
                return 1
            n = t[index]
            print(f'{n["cx"]} {n["cy"]}\t{label(n)} bounds={list(n["bounds"])} matches={len(t)}')
            return 0
    print(f"no element matching {q!r}. Visible labels:", file=sys.stderr)
    seen = [n["text"] or n["desc"] for n in ns if n["text"] or n["desc"]]
    print("  " + " | ".join(dict.fromkeys(seen).keys()) if seen else "  (none)", file=sys.stderr)
    return 1

def main(a):
    if len(a) >= 2 and a[0] == "list":
        return cmd_list(a[1], "--all" in a) or 0
    if len(a) >= 3 and a[0] == "find":
        idx = int(a[a.index("--index") + 1]) if "--index" in a else 0
        return cmd_find(a[1], a[2], "--exact" in a, idx)
    print(__doc__, file=sys.stderr)
    return 2

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
