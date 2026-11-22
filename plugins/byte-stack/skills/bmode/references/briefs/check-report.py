#!/usr/bin/env python3
"""Check a delegate's report against its role's template.

Usage: check-report.py <template> <report.md>

<template> is any brief beside this script but shared-rules (see fill-brief.py). Reads the
required headings and the allowed status or verdict values from the template's report block, so
the template stays the one source. Fails when the report misses a heading, has no status or
verdict line, gives a value the template doesn't allow, or names no `path:line` place where one
is needed. For docs-review-refuter it also reads the JSON verdict list: each entry needs an index,
`upheld` or `refuted`, and evidence with a `path:line`. Prints one line per problem, then PASS or
FAIL. Exit 0 on PASS, 1 on FAIL.
"""
import json, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
ROLES = sorted(f.stem for f in HERE.glob("*.md") if f.name != "shared-rules.md")
PLACE = re.compile(r"[\w./-]+\.\w+:\d+")


def spec(role):
    text = (HERE / f"{role}.md").read_text()
    block = text.split("````markdown", 1)[1].split("\n````", 1)[0]
    headings = [h for h in re.findall(r"^## (.+)$", block, re.M)]
    label, values = re.search(r"^\*\*(Status|Verdict):\*\* (.+)$", block, re.M).groups()
    return headings, label, [v.strip() for v in values.split("|")]


def verdicts(report):
    """Problems with the refuter's JSON verdict list."""
    block = re.search(r"```json\n(.*?)\n```", report, re.S)
    try:
        entries = json.loads(block.group(1)) if block else None
    except json.JSONDecodeError as e:
        return [f"the verdict list isn't JSON: {e}"]
    if not isinstance(entries, list):
        return ["no ```json verdict list"]
    problems = []
    for n, e in enumerate(entries):
        if not isinstance(e, dict) or e.get("index") != n:
            problems.append(f"entry {n}: index isn't {n}")
        elif e.get("verdict") not in ("upheld", "refuted"):
            problems.append(f"entry {n}: verdict isn't upheld or refuted")
        elif not PLACE.search(str(e.get("evidence", ""))):
            problems.append(f"entry {n}: evidence names no path:line")
    return problems


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ROLES or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0 if sys.argv[1:2] in (["-h"], ["--help"]) else 2)
    role, report = sys.argv[1], pathlib.Path(sys.argv[2]).read_text()
    headings, label, allowed = spec(role)
    problems = []

    for h in headings:
        title = h.split(",")[0].strip()
        if not re.search(rf"^## {re.escape(title)}", report, re.M):
            problems.append(f"missing heading: ## {h}")

    found = re.search(rf"^\*\*{label}:\*\*\s*(.+)$", report, re.M)
    value = found.group(1).strip() if found else None
    if value is None:
        problems.append(f"no **{label}:** line")
    elif value not in allowed:
        problems.append(f"{label} is '{value}', not one of {', '.join(allowed)}")

    if role == "docs-review-refuter":
        problems += verdicts(report)
    needs_place = {
        "scout": True,
        "reviewer": "No findings." not in report and value != "PASS",
        "implementor": value == "DONE",
        "gen-issue-decider": value == "COMPLETE",
    }.get(role, False)  # the finder's places are in its findings file; the refuter's are checked above
    if needs_place and not PLACE.search(report):
        problems.append("no path:line place anywhere in the report")

    for p in problems:
        print(f"- {p}")
    print("FAIL" if problems else "PASS")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
