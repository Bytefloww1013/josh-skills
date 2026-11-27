#!/usr/bin/env python3
"""Deterministically validate, diff, and scaffold repo-owned .byte-stack/ playbooks and workflows."""
import argparse
import difflib
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

HERE = Path(__file__).resolve().parent
# The trusted resolver is part of this installed skill, even under python3 -I.
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
from assets import checked, checkout, inspect_file, parse_frontmatter, validate_key

SCHEMA_VERSION = 1
MANAGED_BY = "byte-stack/capture"
ALLOWED_KINDS = ("playbooks", "workflows")
SCHEMA_PATH = HERE.parent / "references" / "capture-payload.schema.json"
KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*\.md$")
LINE_BREAK = re.compile(r"[\n\r\x0b\x0c\x1c-\x1e\x85\u2028\u2029]")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

ALLOWED_PAYLOAD_KEYS = {
    "schema_version",
    "kind",
    "key",
    "title",
    "use_when",
    "prerequisites",
    "steps",
    "verification",
    "guardrails",
}
REQUIRED_PAYLOAD_KEYS = ("schema_version", "kind", "key", "title", "steps", "verification")
ALLOWED_FRONTMATTER_KEYS = {
    "schema-version",
    "kind",
    "key",
    "use-when",
    "managed-by",
    "content-sha256",
}
LIST_SPECS = {
    "prerequisites": (0, 10, 3, 240),
    "steps": (1, 15, 5, 400),
    "verification": (1, 10, 3, 240),
    "guardrails": (0, 10, 3, 240),
}
LOCAL_PATH_PATTERNS = (
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"[A-Za-z]:\\Users\\"),
)
SECRET_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def _check_safety_patterns(label, text, errors):
    for pat in LOCAL_PATH_PATTERNS:
        if pat.search(text):
            errors.append(f"{label} must not contain a machine-local home path")
            break
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            errors.append(f"{label} appears to contain a secret or credential")
            break


def _validate_text_field(label, value, min_len, max_len, errors, *, forbid_delimiter=False):
    if not isinstance(value, str):
        errors.append(f"{label} must be a string")
        return
    if LINE_BREAK.search(value):
        errors.append(f"{label} must be a single line")
        return
    stripped = value.strip()
    if not stripped:
        errors.append(f"{label} must not be empty")
        return
    if (forbid_delimiter and "---" in value) or stripped == "---":
        errors.append(f"{label} must not contain frontmatter delimiter '---'")
    if len(stripped) < min_len or len(value) > max_len:
        errors.append(f"{label} length must be {min_len}..{max_len} characters")
    _check_safety_patterns(label, value, errors)


def validate_payload(data):
    """Validate a JSON extraction payload against capture-payload.schema.json and safety guards."""
    if not isinstance(data, dict):
        return ["payload must be a JSON object"]

    errors = []
    unknown = sorted(set(data.keys()) - ALLOWED_PAYLOAD_KEYS)
    if unknown:
        errors.append(f"unknown payload field(s): {', '.join(unknown)}")

    for req in REQUIRED_PAYLOAD_KEYS:
        if req not in data:
            errors.append(f"missing required field: {req}")

    if "schema_version" in data:
        sv = data["schema_version"]
        if isinstance(sv, bool) or not isinstance(sv, int) or sv != SCHEMA_VERSION:
            errors.append(f"schema_version must be integer {SCHEMA_VERSION}")

    kind = data.get("kind")
    if "kind" in data and (not isinstance(kind, str) or kind not in ALLOWED_KINDS):
        errors.append(f"kind must be one of: {', '.join(ALLOWED_KINDS)}")

    if "key" in data:
        key = data["key"]
        if not isinstance(key, str):
            errors.append("key must be a string")
        elif LINE_BREAK.search(key) or "---" in key:
            errors.append("key must be a single line without '---'")
        elif not (4 <= len(key) <= 120) or not KEY_PATTERN.fullmatch(key):
            errors.append("key must be lowercase kebab-case path ending in .md (4..120 chars)")
        else:
            try:
                validate_key(kind if kind in ALLOWED_KINDS else "playbooks", key)
            except ValueError as err:
                errors.append(str(err))

    if "title" in data:
        _validate_text_field("title", data["title"], 3, 80, errors, forbid_delimiter=True)

    if kind == "playbooks" and "use_when" not in data:
        errors.append("use_when is required when kind is 'playbooks'")
    if "use_when" in data:
        _validate_text_field("use_when", data["use_when"], 10, 200, errors, forbid_delimiter=True)

    for field, (min_items, max_items, min_len, max_len) in LIST_SPECS.items():
        if field not in data:
            continue
        items = data[field]
        if not isinstance(items, list):
            errors.append(f"{field} must be an array of strings")
            continue
        if len(items) < min_items or len(items) > max_items:
            errors.append(f"{field} must contain {min_items}..{max_items} item(s)")
        for idx, item in enumerate(items):
            _validate_text_field(f"{field}[{idx}]", item, min_len, max_len, errors)

    return errors


def format_frontmatter_value(value):
    """Format a single-line scalar YAML frontmatter value so parse_frontmatter round-trips it."""
    if (
        value == ""
        or value != value.strip()
        or ": " in value
        or " #" in value
        or value.endswith(":")
        or value[0] in "\"'[{>|!&*?-%@#"
    ):
        return json.dumps(value, ensure_ascii=False)
    return value


def strip_hash_line(text):
    """Remove only the `content-sha256:` frontmatter line, returning (stripped_text, stored_hex)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return text, None
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].rstrip("\r\n") == "---":
            end_idx = idx
            break
    if end_idx is None:
        return text, None
    stored = None
    kept = []
    for idx, line in enumerate(lines):
        if 0 < idx < end_idx:
            stripped = line.rstrip("\r\n")
            if ":" in stripped and not stripped.startswith((" ", "\t", "-")):
                k, v = stripped.split(":", 1)
                if k.strip() == "content-sha256" and stored is None:
                    stored = v.strip()
                    continue
        kept.append(line)
    return "".join(kept), stored


def compute_content_sha256(text_without_hash):
    """Compute canonical SHA-256 hex digest over UTF-8 bytes without the hash line."""
    return hashlib.sha256(text_without_hash.encode("utf-8")).hexdigest()


def render_playbook(payload):
    """Render a validated payload into canonical LF Markdown with frontmatter integrity hash."""
    kind = payload["kind"]
    key = payload["key"]
    title = payload["title"].strip()
    use_when = payload["use_when"].strip() if "use_when" in payload else None
    prerequisites = [item.strip() for item in payload.get("prerequisites", [])]
    steps = [item.strip() for item in payload["steps"]]
    verification = [item.strip() for item in payload["verification"]]
    guardrails = [item.strip() for item in payload.get("guardrails", [])]

    fm_lines = [
        "---",
        f"schema-version: {SCHEMA_VERSION}",
        f"kind: {kind}",
        f"key: {key}",
    ]
    if use_when is not None:
        fm_lines.append(f"use-when: {format_frontmatter_value(use_when)}")
    fm_lines.append(f"managed-by: {MANAGED_BY}")
    fm_lines.append("---")

    body_lines = [f"# {title}"]
    if prerequisites:
        body_lines.extend(["", "## Prerequisites", ""])
        body_lines.extend(f"- {item}" for item in prerequisites)
    body_lines.extend(["", "## Steps", ""])
    body_lines.extend(f"{idx}. {item}" for idx, item in enumerate(steps, 1))
    body_lines.extend(["", "## Verification", ""])
    body_lines.extend(f"- {item}" for item in verification)
    if guardrails:
        body_lines.extend(["", "## Guardrails", ""])
        body_lines.extend(f"- {item}" for item in guardrails)

    without_hash = "\n".join(fm_lines + [""] + body_lines) + "\n"
    digest = compute_content_sha256(without_hash)
    final_fm = fm_lines[:-1] + [f"content-sha256: {digest}", "---"]
    rendered = "\n".join(final_fm + [""] + body_lines) + "\n"

    meta, _ = parse_frontmatter(rendered, Path(key))
    if use_when is not None and meta.get("use-when") != use_when:
        raise ValueError("rendered frontmatter failed round-trip check")
    return rendered


def _section_items(body_lines, heading):
    target = f"## {heading}"
    start = None
    for idx, line in enumerate(body_lines):
        if line == target:
            start = idx + 1
            break
    if start is None:
        return None
    items = []
    for line in body_lines[start:]:
        if line.startswith("## "):
            break
        if re.match(r"^(?:\d+\.|-|\*)\s+\S", line):
            items.append(line)
    return items


def validate_playbook_text(text, *, expected_kind=None, expected_key=None):
    """Strictly validate a generated .byte-stack/ playbook or workflow Markdown document."""
    label = Path(expected_key or "<playbook>")
    try:
        meta, body = parse_frontmatter(text, label)
    except ValueError as err:
        return [str(err)]

    if not meta:
        return ["missing YAML frontmatter"]

    errors = []
    unknown = sorted(set(meta.keys()) - ALLOWED_FRONTMATTER_KEYS)
    if unknown:
        errors.append(f"unknown frontmatter key(s): {', '.join(unknown)}")

    if meta.get("schema-version") != str(SCHEMA_VERSION):
        errors.append(f"frontmatter schema-version must be '{SCHEMA_VERSION}'")

    kind = meta.get("kind")
    if kind not in ALLOWED_KINDS:
        errors.append(f"frontmatter kind must be one of: {', '.join(ALLOWED_KINDS)}")
    elif expected_kind and kind != expected_kind:
        errors.append(f"frontmatter kind '{kind}' does not match expected '{expected_kind}'")

    key = meta.get("key")
    if not key or not KEY_PATTERN.fullmatch(key):
        errors.append("frontmatter key must be a lowercase kebab-case .md path")
    else:
        try:
            validate_key(kind if kind in ALLOWED_KINDS else "playbooks", key)
        except ValueError as err:
            errors.append(str(err))
        if expected_key and key != expected_key:
            errors.append(f"frontmatter key '{key}' does not match expected '{expected_key}'")

    if meta.get("managed-by") != MANAGED_BY:
        errors.append(f"frontmatter managed-by must be '{MANAGED_BY}'")

    use_when = meta.get("use-when")
    if kind == "playbooks":
        if not use_when or not (10 <= len(use_when.strip()) <= 200):
            errors.append("frontmatter use-when is required for playbooks (10..200 chars)")
    elif use_when is not None and not (10 <= len(use_when.strip()) <= 200):
        errors.append("frontmatter use-when must be 10..200 chars when present")

    body_lines = body.splitlines()
    for line in body_lines:
        if line.startswith("Use when: "):
            body_trigger = line.removeprefix("Use when: ").strip()
            if not use_when or body_trigger != use_when.strip():
                errors.append("body 'Use when: ' conflicts with frontmatter use-when")
            break

    stripped, stored = strip_hash_line(text)
    if not stored or not SHA256_HEX.fullmatch(stored):
        errors.append("frontmatter content-sha256 must be a 64-character lowercase hex digest")
    elif not hmac.compare_digest(stored, compute_content_sha256(stripped)):
        errors.append("content-sha256 mismatch (file was manually edited or corrupted)")

    non_empty = [line for line in body_lines if line.strip()]
    if not non_empty or not re.match(r"^# \S", non_empty[0]):
        errors.append("body must begin with an H1 heading (# Title)")

    steps_items = _section_items(body_lines, "Steps")
    if steps_items is None:
        errors.append("missing '## Steps' section")
    elif not steps_items:
        errors.append("'## Steps' section must contain at least one item")

    verify_items = _section_items(body_lines, "Verification")
    if verify_items is None:
        errors.append("missing '## Verification' section")
    elif not verify_items:
        errors.append("'## Verification' section must contain at least one item")

    if use_when:
        _check_safety_patterns("use-when", use_when, errors)
    _check_safety_patterns("body", body, errors)
    return errors


def plan_write(existing_text, rendered, *, target_label, update, force):
    """Compute deterministic write action, unified diff, and exit code without touching disk."""
    from_label = "/dev/null" if existing_text is None else f"a/{target_label}"
    to_label = f"b/{target_label}"
    diff = "".join(
        difflib.unified_diff(
            (existing_text or "").splitlines(keepends=True),
            rendered.splitlines(keepends=True),
            fromfile=from_label,
            tofile=to_label,
        )
    )

    if existing_text is None:
        return {
            "status": "create",
            "exit_code": 0,
            "write": True,
            "diff": diff,
            "reason": "new playbook",
        }

    if existing_text == rendered:
        return {
            "status": "unchanged",
            "exit_code": 0,
            "write": False,
            "diff": "",
            "reason": "already up to date",
        }

    clean_managed = False
    is_managed = False
    try:
        meta, _ = parse_frontmatter(existing_text, Path(target_label))
        is_managed = meta.get("managed-by") == MANAGED_BY
        stripped, stored = strip_hash_line(existing_text)
        if is_managed and stored and SHA256_HEX.fullmatch(stored):
            clean_managed = hmac.compare_digest(stored, compute_content_sha256(stripped))
    except ValueError:
        pass

    if clean_managed:
        if update or force:
            return {
                "status": "update",
                "exit_code": 0,
                "write": True,
                "diff": diff,
                "reason": "clean managed update",
            }
        return {
            "status": "conflict",
            "exit_code": 3,
            "write": False,
            "diff": diff,
            "reason": "existing managed playbook differs; pass --update to apply",
        }

    origin = "managed-modified" if is_managed else "manual"
    if force:
        return {
            "status": "force-overwrite",
            "exit_code": 0,
            "write": True,
            "diff": diff,
            "reason": f"forced overwrite of {origin} file",
        }
    return {
        "status": "conflict",
        "exit_code": 3,
        "write": False,
        "diff": diff,
        "reason": f"refusing to overwrite {origin} file without --force",
    }


def apply_write(repo, parts, kind, rendered):
    """Atomically write rendered content after checking every path segment for symlinks."""
    target = checked(repo, [".byte-stack", kind, *parts])
    existing_mode = stat.S_IMODE(target.lstat().st_mode) if target.exists() else None
    target.parent.mkdir(parents=True, exist_ok=True)
    target = checked(repo, [".byte-stack", kind, *parts])
    fd, tmp_name = tempfile.mkstemp(prefix=".capture-", suffix=".tmp", dir=target.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
        if existing_mode is not None:
            mode = existing_mode
        else:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    inspect_file(target, kind)
    return target


def _infer_expected_from_path(path, explicit_kind):
    parts = path.parts
    if ".byte-stack" in parts:
        idx = parts.index(".byte-stack")
        if idx + 1 < len(parts) and parts[idx + 1] in ALLOWED_KINDS:
            inferred_kind = parts[idx + 1]
            rel_parts = parts[idx + 2 :]
            inferred_key = "/".join(rel_parts) if rel_parts else None
            return explicit_kind or inferred_kind, inferred_key
    if explicit_kind:
        return explicit_kind, None
    if path.parent.name in ALLOWED_KINDS:
        return path.parent.name, None
    return None, None


def _check_existing_path_is_regular(path):
    if path.is_symlink():
        raise ValueError(f"symlink in asset path: {path}")
    if path.exists() and not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"expected regular file: {path}")


def cmd_write(args):
    try:
        raw = sys.stdin.read() if args.stdin else args.payload.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, ValueError) as err:
        print(f"invalid payload JSON: {err}", file=sys.stderr)
        return 1

    payload_errors = validate_payload(payload)
    if payload_errors:
        if args.json:
            print(json.dumps({"status": "invalid", "errors": payload_errors}, indent=2))
        else:
            for err in payload_errors:
                print(f"payload error: {err}", file=sys.stderr)
        return 1

    kind = payload["kind"]
    key = payload["key"]

    try:
        repo = checkout(args.cwd)
        if repo is None:
            raise ValueError("Run capture inside a Git worktree.")
        parts = validate_key(kind, key)
        target = checked(repo, [".byte-stack", kind, *parts])
        _check_existing_path_is_regular(target)
        existing_text = target.read_text(encoding="utf-8") if target.exists() else None
    except (OSError, ValueError) as err:
        print(str(err), file=sys.stderr)
        return 2

    rendered = render_playbook(payload)
    self_errors = validate_playbook_text(rendered, expected_kind=kind, expected_key=key)
    if self_errors:
        print("; ".join(self_errors), file=sys.stderr)
        return 1

    target_rel = str(target.relative_to(repo))
    plan = plan_write(
        existing_text,
        rendered,
        target_label=target_rel,
        update=args.update,
        force=args.force,
    )

    if not args.dry_run and plan["write"]:
        try:
            apply_write(repo, parts, kind, rendered)
        except (OSError, ValueError) as err:
            print(str(err), file=sys.stderr)
            return 2

    result = {
        "status": plan["status"],
        "dry_run": args.dry_run,
        "path": str(target),
        "relative_path": target_rel,
        "kind": kind,
        "key": key,
        "reason": plan["reason"],
        "diff": plan["diff"],
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        prefix = "dry-run " if args.dry_run else ""
        print(f"{prefix}{plan['status']}: {target_rel} ({plan['reason']})")
        if plan["diff"]:
            print(plan["diff"], end="" if plan["diff"].endswith("\n") else "\n")
    return plan["exit_code"]


def cmd_validate(args):
    path = args.path
    try:
        for parent in [path, *path.parents]:
            if parent.name == ".byte-stack" or ".byte-stack" in parent.parts:
                if parent.is_symlink():
                    raise ValueError(f"symlink in asset path: {parent}")
            if parent == path and path.is_symlink():
                raise ValueError(f"symlink in asset path: {path}")
        if not path.exists():
            raise ValueError(f"missing file: {path}")
        _check_existing_path_is_regular(path)
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as err:
        print(str(err), file=sys.stderr)
        return 2

    expected_kind, expected_key = _infer_expected_from_path(path, args.kind)
    errors = validate_playbook_text(text, expected_kind=expected_kind, expected_key=expected_key)
    if not errors:
        try:
            meta, _ = parse_frontmatter(text, path)
            inspect_file(path, expected_kind or meta.get("kind", "playbooks"))
        except ValueError as err:
            errors.append(str(err))

    if args.json:
        print(json.dumps({"valid": not errors, "path": str(path), "errors": errors}, indent=2))
    elif errors:
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        print("INVALID", file=sys.stderr)
    else:
        print(f"VALID: {path}")
    return 0 if not errors else 1


def cmd_schema():
    print(SCHEMA_PATH.read_text(encoding="utf-8"), end="")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    write_p = sub.add_parser("write", help="Validate payload and write or preview a .byte-stack/ asset")
    src = write_p.add_mutually_exclusive_group(required=True)
    src.add_argument("--payload", type=Path, help="Path to JSON payload matching capture-payload.schema.json")
    src.add_argument("--stdin", action="store_true", help="Read JSON payload from stdin")
    write_p.add_argument("--dry-run", action="store_true", help="Preview diff and plan without writing")
    write_p.add_argument("--update", action="store_true", help="Allow updating an unmodified managed file")
    write_p.add_argument("--force", action="store_true", help="Allow overwriting a manually modified or hand-authored file")
    write_p.add_argument("--json", action="store_true", help="Print structured JSON result")
    write_p.add_argument("--cwd", type=Path, default=Path.cwd(), help="Directory inside target Git worktree")

    val_p = sub.add_parser("validate", help="Strictly validate a captured .byte-stack/ Markdown file")
    val_p.add_argument("path", type=Path, help="Path to Markdown file to validate")
    val_p.add_argument("--kind", choices=ALLOWED_KINDS, help="Expected asset kind")
    val_p.add_argument("--json", action="store_true", help="Print structured JSON result")

    sub.add_parser("schema", help="Print the capture-payload JSON Schema")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "write":
        return cmd_write(args)
    if args.command == "validate":
        return cmd_validate(args)
    return cmd_schema()


if __name__ == "__main__":
    sys.exit(main())
