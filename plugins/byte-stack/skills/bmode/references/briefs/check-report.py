#!/usr/bin/env python3
"""Check a delegate's report against its role's template.

Usage: check-report.py <scout|reviewer|implementor> <report.md>

Reads the required headings and the allowed status or verdict values from the template's report
block, so the template stays the one source. Fails when the report misses a heading, has no
status or verdict line, gives a value the template doesn't allow, or names no `path:line` place
where one is needed. Prints one line per problem, then PASS or FAIL. Exit 0 on PASS, 1 on FAIL.
"""
import pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
ROLES = ("scout", "reviewer", "implementor")
PLACE = re.compile(r"[\w./-]+\.\w+:\d+")


def spec(role):
    text = (HERE / f"{role}.md").read_text()
    block = text.split("````markdown", 1)[1].split("\n````", 1)[0]
    headings = [h for h in re.findall(r"^## (.+)$", block, re.M)]
    label, values = re.search(r"^\*\*(Status|Verdict):\*\* (.+)$", block, re.M).groups()
    return headings, label, [v.strip() for v in values.split("|")]


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

    needs_place = {
        "scout": True,
        "reviewer": "No findings." not in report and value != "PASS",
        "implementor": value == "DONE",
    }[role]
    if needs_place and not PLACE.search(report):
        problems.append("no path:line place anywhere in the report")

    for p in problems:
        print(f"- {p}")
    print("FAIL" if problems else "PASS")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
