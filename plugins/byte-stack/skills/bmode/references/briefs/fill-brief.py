#!/usr/bin/env python3
"""Fill a delegate brief from its template.

Usage: fill-brief.py <template>
                     --values <file.json> [--set KEY=VALUE ...] [--out <brief.md>]
       fill-brief.py --keys <template>     list what each placeholder of a template takes

A template is a .md file beside this script other than shared-rules.md: scout, reviewer, implementor, and the briefs for one
skill's agents (docs-review-finder, docs-review-refuter, gen-issue-decider). Each one's first line names its policy role.

Fills BASE_SHA, START, EXPECTED_HEAD, CARRY_DIR, BMODE_DIR and READ_CAP (and REPO_ROOT for every template but reviewer) when
not given, inlines shared-rules.md as SHARED_RULES, and uses the tools available in the target checkout. FINDINGS takes the path of
quote-checked findings (or its JSON) and keeps only each finding's index, doc and code: the refuter never sees the rest.
Exits 1 on a placeholder left unfilled or a value no template uses. Prints the brief, and writes it to --out (default
RUN_DIR/brief.md).
"""
import argparse, json, pathlib, re, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
# The trusted resolver is part of this installed skill, even under python -I.
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
sys.dont_write_bytecode = True
from assets import resolve


def template_text(name):
    _, path = resolve(pathlib.Path.cwd(), "references", f"briefs/{name}.md")
    return path.read_text(encoding="utf-8")


TEMPLATES = sorted(f.stem for f in HERE.glob("*.md") if f.name != "shared-rules.md")
TOKEN = re.compile(r"\{\{([A-Z_]+)\}\}")

KEYS = {
    "TASK_ID": "short unique task ID",
    "RUN_DIR": "absolute path: a task-specific scratch directory",
    "REPO_ROOT": "absolute checkout path the delegate works in (required for a reviewer; default for the rest: the current checkout)",
    "READ_CAP": "files beyond those the task names (default 40; raise it for a wide diff)",
    "CONSUMER": "who reads the scout report: implementor, reviewer or coordinator",
    "QUESTIONS": "numbered questions, each answerable with a path and lines (JSON list = one per line)",
    "START_AREAS": "known folders, files or symbols, or 'unknown'",
    "BASE": "base SHA of the change (base commit at review time)",
    "HEAD": "head SHA of the change, never a branch name",
    "GOAL": "what the change is for, in one or two sentences",
    "ISSUE": "#N and its title, or 'none'",
    "ISSUE_NUMBER": "the issue number, or none",
    "BRANCH": "branch named by the branch rule in the target repository",
    "BASE_SHA": "base commit for the work (default: checkout HEAD)",
    "START": "new, or continue for a fix pass or a retry on a branch that exists",
    "EXPECTED_HEAD": "BASE_SHA for new work; for continue, the branch head the coordinator last checked",
    "CARRY_DIR": "absolute folder of git-ignored files saved from the last worktree, or 'none'",
    "DOOR": "reversibility and impact, from the task or issue",
    "PLAN_PATH": "absolute path to the plan, or 'none: the spec below is the plan'",
    "SPEC": "exact changes: paths, symbols, invariants, target behaviour, from scout or reviewer evidence",
    "OWNED_FILES": "files or one narrow folder the implementor may change",
    "BMODE_DIR": "absolute path of the coordinator's byte-stack skills/bmode folder (default: the one holding this script)",
    "PLAYBOOK": "feature.md, bug-fix.md or refactoring.md",
    "EXTRA_CONSTRAINTS": "task-specific limits, or 'none'",
    "BUNDLE": "absolute path of the documentation and source bundle",
    "DOC_SCOPE": "'every doc in the bundle', or the doc paths this finder alone reviews when the bundle is split",
    "FINDER_N": "this finder's number, 1 to 3; it writes RUN_DIR/findings-<n>.json",
    "FINDINGS": "absolute path of quote-checked findings (or its JSON); only each finding's doc and code reach the brief",
    "REQUEST": "the user's request, word for word",
    "QUESTION": "the one question to settle, a single decision",
    "CONTEXT": "what was gathered for the question: paths and line ranges, doc and ADR names (JSON list = one per line)",
    "EARLIER": "earlier questions with the user's answers, or 'none'",
}

def barrier(value):
    """Keep only each finding's doc and code quotes, numbered: never the finder's why, cause or pr."""
    data = value
    if isinstance(value, str):
        data = json.loads(value if value.lstrip()[:1] in ("[", "{") else pathlib.Path(value).read_text())
    findings = data["findings"] if isinstance(data, dict) else data
    keep = lambda q: {k: q[k] for k in ("file", "line", "quote")}
    return json.dumps([{"index": i, "doc": keep(f["doc"]), "code": keep(f["code"])} for i, f in enumerate(findings)], indent=2)

def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    if len(sys.argv) == 3 and sys.argv[1] == "--keys":
        if sys.argv[2] not in TEMPLATES:
            sys.exit(f"--keys takes one of: {', '.join(TEMPLATES)}")
        shared = template_text("shared-rules")
        template = template_text(sys.argv[2]).replace("{{SHARED_RULES}}", shared.strip())
        used = sorted(set(TOKEN.findall(template)) - {"CODEGRAPH_LINE"})
        for k in used:
            print(f"{k}: {KEYS.get(k, '(no description)')}")
        return
    p.add_argument("role", choices=TEMPLATES)
    p.add_argument("--provider", help=argparse.SUPPRESS)  # accepted for older callers
    p.add_argument("--values", type=pathlib.Path)
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("--out", type=pathlib.Path)
    a = p.parse_args()

    values = json.loads(a.values.read_text()) if a.values else {}
    for kv in a.set:
        k, _, v = kv.partition("=")
        values[k] = v
    if "FINDINGS" in values:
        values["FINDINGS"] = barrier(values["FINDINGS"])
    values = {k: v if isinstance(v, str) else "\n".join(v) if isinstance(v, list) and all(isinstance(x, str) for x in v)
              else json.dumps(v, indent=2) for k, v in values.items()}
    template = template_text(a.role)
    shared = template_text("shared-rules")
    text = template.replace("{{SHARED_RULES}}", shared.strip())
    used = set(TOKEN.findall(text))
    defaults = {"READ_CAP": "40", "START": "new", "CARRY_DIR": "none",
                "BMODE_DIR": str(HERE.parents[1]), "CODEGRAPH_LINE": "Use the checkout's available search tools."}
    for key, value in defaults.items():
        if key in used:
            values.setdefault(key, value)
    if "REPO_ROOT" in used and "REPO_ROOT" not in values and a.role != "reviewer":
        values["REPO_ROOT"] = git("rev-parse", "--show-toplevel")
    if "BASE_SHA" in used and "BASE_SHA" not in values:
        values["BASE_SHA"] = git("rev-parse", "HEAD")
    if "EXPECTED_HEAD" in used and "BASE_SHA" in values:
        values.setdefault("EXPECTED_HEAD", values["BASE_SHA"])

    unknown = sorted(set(values) - used - {"SHARED_RULES"})
    missing = sorted(used - set(values))
    if unknown or missing:
        if missing:
            print(f"unfilled: {', '.join(missing)}", file=sys.stderr)
        if unknown:
            print(f"not in the {a.role} template: {', '.join(unknown)}", file=sys.stderr)
        sys.exit(1)

    text = TOKEN.sub(lambda m: values[m.group(1)], text)
    if not a.out and "RUN_DIR" not in values:
        p.error("use --out for a template without RUN_DIR")
    out = a.out or pathlib.Path(values["RUN_DIR"]) / "brief.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(text)

if __name__ == "__main__":
    main()
