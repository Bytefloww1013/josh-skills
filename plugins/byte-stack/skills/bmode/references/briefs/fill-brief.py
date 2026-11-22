#!/usr/bin/env python3
"""Fill a delegate brief from its template.

Usage: fill-brief.py <scout|reviewer|implementor> --provider <claude|antigravity|opencode|codex>
                     --values <file.json> [--set KEY=VALUE ...] [--out <brief.md>]
       fill-brief.py --keys <role>     list what each placeholder of a role takes

Fills BASE_SHA, EXPECTED_HEAD, BMODE_DIR and READ_CAP (and REPO_ROOT for a scout) when not given, inlines
shared-rules.md as SHARED_RULES, and writes the CodeGraph line for the provider. Exits 1 on a placeholder left unfilled or a
value no template uses. Prints the brief, and writes it to --out (default RUN_DIR/brief.md).
"""
import argparse, json, pathlib, re, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
TOKEN = re.compile(r"\{\{([A-Z_]+)\}\}")
CODEGRAPH = {
    "claude": "Call the `codegraph_explore` MCP tool before you read or search code.",
    "other": 'Run `codegraph explore "<symbols or question>"` in the shell before you read or search code.',
}

KEYS = {
    "TASK_ID": "short unique id, e.g. issue712-impl-1",
    "RUN_DIR": "absolute path: <coordinator checkout>/tmp/agents/<task>/<run>",
    "REPO_ROOT": "absolute checkout path: the delegate's worktree (required for implementor and reviewer; default for a scout: the current checkout)",
    "READ_CAP": "files beyond those the task names (default 40; raise it for a wide diff)",
    "CONSUMER": "who reads the scout report: implementor, reviewer or coordinator",
    "QUESTIONS": "numbered questions, each answerable with a path and lines (JSON list = one per line)",
    "START_AREAS": "known folders, files or symbols, or 'unknown'",
    "BASE": "base SHA of the change (origin/main at review time)",
    "HEAD": "head SHA of the change, never a branch name",
    "GOAL": "what the change is for, in one or two sentences",
    "ISSUE": "#N and its title, or 'none'",
    "ISSUE_NUMBER": "the issue number alone, e.g. 734",
    "BRANCH": "branch named by the branch rule in docs/directives/git-and-prs.md",
    "BASE_SHA": "origin/main SHA the branch starts from (default: git rev-parse origin/main)",
    "EXPECTED_HEAD": "BASE_SHA for new work; the last head the coordinator checked for a fix pass",
    "DOOR": "one-way-door or two-way-door, from the issue's label",
    "PLAN_PATH": "absolute path to the plan, or 'none: the spec below is the plan'",
    "SPEC": "exact changes: paths, symbols, invariants, target behaviour, from scout or reviewer evidence",
    "OWNED_FILES": "files or one narrow folder the implementor may change",
    "BMODE_DIR": "absolute path of the coordinator's byte-stack skills/bmode folder (default: the one holding this script)",
    "PLAYBOOK": "feature.md, bug-fix.md or refactoring.md",
    "EXTRA_CONSTRAINTS": "task-specific limits, or 'none'",
}

def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    if len(sys.argv) == 3 and sys.argv[1] == "--keys":
        if sys.argv[2] not in ("scout", "reviewer", "implementor"):
            sys.exit("--keys takes scout, reviewer or implementor")
        shared = (HERE / "shared-rules.md").read_text()
        used = sorted(set(TOKEN.findall((HERE / f"{sys.argv[2]}.md").read_text() + shared)) - {"SHARED_RULES", "CODEGRAPH_LINE"})
        for k in used:
            print(f"{k}: {KEYS.get(k, '(no description)')}")
        return
    p.add_argument("role", choices=["scout", "reviewer", "implementor"])
    p.add_argument("--provider", required=True, choices=["claude", "antigravity", "opencode", "codex"])
    p.add_argument("--values", type=pathlib.Path)
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("--out", type=pathlib.Path)
    a = p.parse_args()

    values = json.loads(a.values.read_text()) if a.values else {}
    for kv in a.set:
        k, _, v = kv.partition("=")
        values[k] = v
    values = {k: "\n".join(v) if isinstance(v, list) else str(v) for k, v in values.items()}
    if a.role == "scout":
        values.setdefault("REPO_ROOT", git("rev-parse", "--show-toplevel"))
    values.setdefault("READ_CAP", "40")
    values.setdefault("CODEGRAPH_LINE", CODEGRAPH["claude" if a.provider == "claude" else "other"])
    if a.role == "implementor":
        values.setdefault("BASE_SHA", git("rev-parse", "origin/main"))
        values.setdefault("EXPECTED_HEAD", values["BASE_SHA"])
        values.setdefault("BMODE_DIR", str(HERE.parent.parent))

    template = (HERE / f"{a.role}.md").read_text()
    shared = (HERE / "shared-rules.md").read_text()
    text = template.replace("{{SHARED_RULES}}", shared.strip())

    used = set(TOKEN.findall(text))
    unknown = sorted(set(values) - used - {"SHARED_RULES"})
    missing = sorted(used - set(values))
    if unknown or missing:
        if missing:
            print(f"unfilled: {', '.join(missing)}", file=sys.stderr)
        if unknown:
            print(f"not in the {a.role} template: {', '.join(unknown)}", file=sys.stderr)
        sys.exit(1)

    text = TOKEN.sub(lambda m: values[m.group(1)], text)
    out = a.out or pathlib.Path(values["RUN_DIR"]) / "brief.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(text)

if __name__ == "__main__":
    main()
