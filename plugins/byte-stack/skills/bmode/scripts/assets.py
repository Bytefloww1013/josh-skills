"""Find repository-owned assets and the defaults shipped by an installed skill."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess

KINDS = ("playbooks", "workflows", "references", "scripts")
SKILL = Path(__file__).resolve().parents[1]
FRONTMATTER_KEY = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def checkout(cwd):
    result = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"})
    if result.returncode == 0:
        return Path(result.stdout.rstrip("\n"))
    if "not a git repository" in result.stderr or "must be run in a work tree" in result.stderr:
        return None
    raise ValueError(result.stderr.strip() or f"cannot identify worktree at {cwd}")


def checked(base, parts):
    path = base
    for part in parts:
        if path.exists() and not path.is_dir():
            raise ValueError(f"expected directory: {path}")
        path = path / part
        if path.is_symlink():
            raise ValueError(f"symlink in asset path: {path}")
    return path


def roots(cwd, kind, owner):
    repo = checkout(cwd)
    if repo:
        parts = [".byte-stack", kind]
        if owner != SKILL:
            parts.append(owner.name)
        yield "repo", checked(repo, parts)
    yield "bundled", owner / kind


def validate_key(kind, key):
    """Validate an asset key and return its path segments."""
    parts = key.split("/")
    if any(not p.isprintable() or p in ("", ".", "..") or "\\" in p or ":" in p for p in parts):
        raise ValueError(f"invalid asset key: {key}")
    if kind in ("playbooks", "workflows") and not key.endswith(".md"):
        raise ValueError(f"expected a Markdown key: {key}")
    return parts


def parse_frontmatter(content, path="<asset>"):
    """Parse flat scalar YAML frontmatter (`key: value`) and return (meta, body)."""
    lines = content.splitlines()
    if not lines or lines[0] != "---":
        return {}, content
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx] == "---":
            end_idx = idx
            break
    if end_idx is None:
        raise ValueError(f"unterminated frontmatter: {path}")
    meta = {}
    for line in lines[1:end_idx]:
        if not line:
            continue
        if line.startswith((" ", "\t", "-")) or ":" not in line:
            raise ValueError(f"invalid frontmatter line: {path}")
        raw_key, raw_val = line.split(":", 1)
        key = raw_key.strip()
        if not FRONTMATTER_KEY.fullmatch(key):
            raise ValueError(f"invalid frontmatter key: {path}")
        if key in meta:
            raise ValueError(f"duplicate frontmatter key '{key}': {path}")
        val = raw_val.strip()
        if val.startswith('"'):
            if len(val) < 2 or not val.endswith('"'):
                raise ValueError(f"invalid frontmatter string: {path}")
            try:
                decoded = json.loads(val)
            except ValueError as error:
                raise ValueError(f"invalid frontmatter string: {path}") from error
            if not isinstance(decoded, str):
                raise ValueError(f"invalid frontmatter string: {path}")
            val = decoded
        elif val.startswith("'"):
            if len(val) < 2 or not val.endswith("'"):
                raise ValueError(f"invalid frontmatter string: {path}")
            val = val[1:-1].replace("''", "'")
        meta[key] = val
    body = "\n".join(lines[end_idx + 1 :])
    return meta, body


def inspect_file(path, kind):
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"expected regular file: {path}")
    if kind == "scripts" or path.suffix != ".md":
        with path.open("rb"):
            pass
        return ""
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"empty asset: {path}")
    meta, body = parse_frontmatter(content, path)
    if not body.strip():
        raise ValueError(f"empty asset: {path}")
    fm_trigger = meta.get("use-when", "").strip()
    body_trigger = ""
    for line in body.splitlines():
        if line.startswith("Use when: "):
            body_trigger = line.removeprefix("Use when: ").strip()
            break
    if fm_trigger and body_trigger and fm_trigger != body_trigger:
        raise ValueError(f"conflicting trigger descriptions: {path}")
    return fm_trigger or body_trigger


def resolve(cwd, kind, key, owner=SKILL):
    parts = validate_key(kind, key)
    for source, base in roots(cwd, kind, owner):
        path = checked(base, parts)
        try:
            inspect_file(path, kind)
        except FileNotFoundError:
            continue
        return source, path
    raise KeyError(key)


def catalog(cwd, kind, owner):
    entries = {}
    for _, base in reversed(list(roots(cwd, kind, owner))):
        if not base.exists():
            continue
        if not base.is_dir():
            raise ValueError(f"expected directory: {base}")
        for path in sorted(base.rglob("*")):
            key = path.relative_to(base)
            if any(part.startswith(".") or part == "__pycache__" for part in key.parts):
                continue
            checked(base, key.parts)
            if path.is_dir() or (kind in ("playbooks", "workflows") and path.suffix != ".md"):
                continue
            trigger = inspect_file(path, kind) or entries.get(str(key), "")
            if kind == "playbooks" and not trigger:
                raise ValueError(f"missing 'Use when: ' description: {path}")
            entries[str(key)] = trigger
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--owner", type=Path, default=SKILL, help="installed directory of the consuming skill")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-playbooks")
    listing = commands.add_parser("list")
    listing.add_argument("kind", choices=KINDS)
    get = commands.add_parser("resolve")
    get.add_argument("kind", choices=KINDS)
    get.add_argument("key")
    args = parser.parse_args()
    owner = args.owner.resolve()
    if not (owner / "SKILL.md").is_file():
        parser.error(f"missing installed skill: {owner}")
    kind = getattr(args, "kind", "playbooks")
    try:
        if args.command == "resolve":
            try:
                source, path = resolve(args.cwd, kind, args.key, owner)
            except KeyError:
                keys = ", ".join(sorted(catalog(args.cwd, kind, owner))) or "(none)"
                parser.exit(1, f"unknown {kind} key: {args.key}. Available: {keys}\n")
            print(f"{source}\t{path}")
        else:
            for key, trigger in sorted(catalog(args.cwd, kind, owner).items()):
                print(f"{key}\t{trigger}".rstrip())
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
