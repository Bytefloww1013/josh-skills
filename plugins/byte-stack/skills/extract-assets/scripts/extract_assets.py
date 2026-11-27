#!/usr/bin/env python3
"""Scan a Git repository and deterministically preview/write .byte-stack/ assets."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
DEFAULT_BMODE = SKILL_DIR.parent / "bmode"
SCHEMA_PATH = SKILL_DIR / "references" / "extract-candidates.schema.json"

SCHEMA_VERSION = 1
ALLOWED_CATEGORIES = ("workflow", "convention", "rule", "knowledge")
ALLOWED_KINDS = ("playbooks", "workflows", "references", "scripts")
ALLOWED_ENVELOPE_KEYS = frozenset({"schema_version", "candidates"})
ALLOWED_CANDIDATE_KEYS = frozenset(
    {"id", "category", "kind", "key", "provenance", "rationale", "payload", "content", "executable"}
)
ALLOWED_PROVENANCE_KEYS = frozenset({"path", "command", "key", "line"})
ALLOWED_PAYLOAD_SUBKEYS = frozenset(
    {"title", "use_when", "prerequisites", "steps", "verification", "guardrails"}
)
PUBLIC_PLAN_KEYS = (
    "category", "dedupe_flags", "diff", "id", "key", "kind", "provenance",
    "reason", "relative_path", "similar_to", "status", "verdict", "verdict_reason",
)

REF_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*\.md$")
SCRIPT_KEY_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[-_][a-z0-9]+)*(?:/[a-z0-9]+(?:[-_][a-z0-9]+)*)*(?:\.[a-z0-9]+)?$"
)
_TOKEN_CHAR_RE = re.compile(r"[A-Za-z0-9_-]")
_PEM_BEGIN_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_PEM_END_RE = re.compile(r"-----END [A-Z ]*PRIVATE KEY-----")

EXTRA_LOCAL_PATH_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9._-])/(?:home|Users)/[A-Za-z0-9._-]+(?=$|[^A-Za-z0-9._-])"),
    re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+(?=$|[^A-Za-z0-9._-])"),
)
REDACT_LOCAL_PATH_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9._-])/(?:home|Users)/[A-Za-z0-9._-]+(?:/[^\s'\"`<>|;,)]*)?"),
    re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+(?:\\[^\s'\"`<>|;,)]*)?"),
)

MAX_CONTENT_BYTES = 65536
MAX_PROVENANCE_READ_BYTES = 1048576
CATALOG_HEAD_BYTES = 4096
DEFAULT_MAX_FILES = 100
DEFAULT_MAX_BYTES = 262144
MAX_SIGNALS_PER_FILE = 30
MAX_SIGNAL_TEXT_LEN = 200

VENDOR_BUILD_DIRS = frozenset({
    "node_modules", "vendor", "third_party", "dist", "build", "target", ".venv",
    "venv", "__pycache__", ".tox", ".nox", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".next", ".nuxt", ".cache", "coverage", "htmlcov", ".gradle",
    "Pods", "bower_components", ".terraform", ".eggs",
})
SECRET_NAME_PATTERNS = (
    re.compile(r"^\.env(?:\..+)?$", re.IGNORECASE),
    re.compile(r"\.(?:pem|key|p12|pfx|jks|keystore|kdbx|secret|secrets)$", re.IGNORECASE),
    re.compile(r"^id_(?:rsa|ed25519|ecdsa|dsa)(?:\..+)?$", re.IGNORECASE),
    re.compile(r"^credentials(?:\..+)?$", re.IGNORECASE),
    re.compile(r".*credentials.*\.(?:json|ya?ml|toml|ini|txt)$", re.IGNORECASE),
    re.compile(r"^secrets?\.(?:json|ya?ml|toml|ini|txt)$", re.IGNORECASE),
    re.compile(r"^service[-_]account.*\.json$", re.IGNORECASE),
    re.compile(r"^\.(?:netrc|npmrc|pypirc|htpasswd)$", re.IGNORECASE),
)
MACHINE_LOCAL_PATTERNS = (
    re.compile(r"^\.local(?:\..+)?$", re.IGNORECASE),
    re.compile(r".+\.local(?:\..+)?$", re.IGNORECASE),
    re.compile(r"^(?:\.DS_Store|Thumbs\.db|Desktop\.ini)$", re.IGNORECASE),
    re.compile(r".+\.(?:swp|swo)$", re.IGNORECASE),
    re.compile(r".+~$"),
)
CI_PATHS = frozenset({
    ".gitlab-ci.yml", ".gitlab-ci.yaml", ".circleci/config.yml", ".circleci/config.yaml",
    "jenkinsfile", "azure-pipelines.yml", "azure-pipelines.yaml", ".travis.yml", "bitbucket-pipelines.yml",
})
HOOK_PATHS = frozenset({
    ".pre-commit-config.yaml", ".pre-commit-config.yml", ".lefthook.yml",
    "lefthook.yml", "lefthook.yaml", ".gitattributes", ".claude/settings.json",
})
STEERING_NAMES = frozenset({"agents.md", "claude.md", "gemini.md", "codex.md", "copilot.md"})
DIRECTIVE_NAMES = frozenset({
    "contributing.md", "glossary.md", "standards.md", "conventions.md", "style.md",
    "styleguide.md", "style-guide.md", "scripts.md", "code_of_conduct.md", "security.md",
})
DIRECTIVE_PATHS = frozenset({
    "docs/standards.md", "docs/conventions.md", "docs/style-guide.md", "docs/styleguide.md",
    "docs/workflow.md", "docs/contributing.md", ".github/contributing.md",
})
TASK_RUNNER_NAMES = frozenset({
    "makefile", "gnumakefile", "justfile", "taskfile.yml", "taskfile.yaml", "package.json",
    "pyproject.toml", "setup.cfg", "tox.ini", "noxfile.py", "cargo.toml", "go.mod",
    "rakefile", "turbo.json", "nx.json", "mise.toml", "procfile",
})
QUALITY_EXACT_NAMES = frozenset({
    ".editorconfig", ".flake8", ".pylintrc", "pylintrc", ".isort.cfg", ".bandit",
    ".shellcheckrc", ".hadolint.yaml", "biome.json", "biome.jsonc", "pyrightconfig.json",
    "jsconfig.json", "oxlint.json", ".oxlintrc.json", "deno.json", "renovate.json",
    "ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini", ".golangci.yml", ".golangci.yaml",
    "rustfmt.toml", ".rustfmt.toml", "clippy.toml", ".clippy.toml", "tsconfig.json",
})
QUALITY_PREFIXES = (
    ".eslintrc", "eslint.config.", ".prettierrc", "prettier.config.",
    "tsconfig.", ".stylelintrc", ".markdownlint", ".yamllint",
)
SCRIPT_DIRS = frozenset({"scripts", "script", "bin", "tools"})
SCRIPT_EXTS = frozenset({".sh", ".bash", ".zsh", ".py", ".ts", ".js", ".mjs", ".cjs", ".rb", ".pl", ".ps1"})
STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "use", "when", "run", "file", "files",
    "repo", "repository", "are", "not", "all", "any", "only", "into", "before", "after",
    "check", "steps", "verification",
})


class DiagnosticError(Exception):
    """Error resulting in exit code 2 (missing bmode, Git, path, or symlink guard)."""


class TargetChangedError(Exception):
    """Per-ID exit-3 conflict when a target file changed on disk after preflight."""


def load_bmode(bmode_arg):
    """Locate and import bmode's assets and capture_playbook modules."""
    bmode_dir = (bmode_arg if bmode_arg is not None else DEFAULT_BMODE).resolve()
    capture_py = bmode_dir / "scripts" / "capture_playbook.py"
    if not (bmode_dir / "SKILL.md").is_file() or not (bmode_dir / "scripts" / "assets.py").is_file() or not capture_py.is_file():
        raise DiagnosticError(
            "missing bmode skill directory (expected SKILL.md, scripts/assets.py, "
            "and scripts/capture_playbook.py); install byte-stack or pass --bmode DIR"
        )
    scripts_dir = str(bmode_dir / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import assets as bmode_assets
    import capture_playbook as bmode_capture

    return bmode_dir, bmode_assets, bmode_capture, capture_py


def _has_local_path(text, bmode_capture):
    return (
        (bmode_capture is not None and any(p.search(text) for p in bmode_capture.LOCAL_PATH_PATTERNS))
        or any(p.search(text) for p in EXTRA_LOCAL_PATH_PATTERNS)
    )


def _contains_sensitive(text, bmode_capture, repo_strings=()):
    return (
        any(n and n in text for n in repo_strings)
        or _has_local_path(text, bmode_capture)
        or (bmode_capture is not None and any(p.search(text) for p in bmode_capture.SECRET_PATTERNS))
    )


def _sanitize_text(text, repo, bmode_dir, bmode_capture, extra_paths=()):
    """Redact repo/bmode roots, machine-local home paths, and secret patterns."""
    out = text
    replacements = []
    for path_obj, token in ((repo, "<repo>"), (bmode_dir, "<bmode>"), *((p, "<cwd>") for p in extra_paths)):
        if path_obj is not None:
            for needle in {str(Path(path_obj).resolve()), str(path_obj)}:
                if needle:
                    replacements.append((needle, token))
    for needle, token in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        out = out.replace(needle, token)
    for pat in REDACT_LOCAL_PATH_PATTERNS:
        out = pat.sub("<local-path>", out)
    if bmode_capture is not None:
        for pat in bmode_capture.LOCAL_PATH_PATTERNS:
            out = pat.sub("<local-path>/", out)
        for pat in bmode_capture.SECRET_PATTERNS:
            out = pat.sub("<redacted-secret>", out)
    return out


def _redact_diff(diff_text, repo, bmode_dir, bmode_capture):
    """Visibly redact diff lines containing secrets, home paths, or the repo root."""
    if not diff_text:
        return ""
    repo_strs = tuple(sorted({str(repo), str(repo.resolve())}, key=len, reverse=True)) if repo is not None else ()
    out, in_pem = [], False
    for line in diff_text.splitlines(keepends=True):
        eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
        body = line[: len(line) - len(eol)] if eol else line
        if body.startswith(("--- ", "+++ ", "@@ ")) or not body or body[0] not in ("-", "+", " "):
            out.append(_sanitize_text(body, repo, bmode_dir, bmode_capture) + eol)
            continue
        prefix, content = body[0], body[1:]
        if _PEM_BEGIN_RE.search(content):
            in_pem = True
            out.append(f"{prefix}[REDACTED: sensitive content]{eol}")
        elif in_pem:
            if _PEM_END_RE.search(content):
                in_pem = False
            out.append(f"{prefix}[REDACTED: sensitive content]{eol}")
        elif _contains_sensitive(content, bmode_capture, repo_strs):
            out.append(f"{prefix}[REDACTED: sensitive content]{eol}")
        else:
            out.append(line)
    return "".join(out)


def _check_utf8(label, text, errors):
    try:
        text.encode("utf-8")
        return True
    except UnicodeEncodeError:
        errors.append(f"{label} must contain valid UTF-8 characters (no lone surrogates)")
        return False


def _check_safety_patterns(bmode_capture, label, text, errors):
    if _has_local_path(text, bmode_capture):
        errors.append(f"{label} must not contain a machine-local home path")
    if bmode_capture is not None and any(p.search(text) for p in bmode_capture.SECRET_PATTERNS):
        errors.append(f"{label} appears to contain a secret or credential")


def _check_regular(path):
    if path.is_symlink():
        raise ValueError(f"symlink in asset path: {path}")
    if path.exists() and not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"expected regular file: {path}")


def list_tracked_files(repo):
    """Return sorted list of (rel_posix_path, mode) from `git ls-files -s -z`."""
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-s", "-z"],
        capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"},
    )
    if result.returncode != 0:
        raise DiagnosticError(result.stderr.strip() or "git ls-files failed")
    seen = {}
    for entry in result.stdout.split("\0"):
        if "\t" in entry:
            meta, rel_path = entry.split("\t", 1)
            parts = meta.split()
            if parts and rel_path not in seen:
                seen[rel_path] = parts[0]
    return sorted(seen.items(), key=lambda item: item[0])


def exclusion_reason(rel_path, mode):
    """Return exclusion reason string for a path (checking every segment), or None."""
    if mode == "120000":
        return "symlink"
    if mode == "160000":
        return "submodule"
    parts = rel_path.split("/")
    if any(part in VENDOR_BUILD_DIRS for part in parts[:-1]):
        return "vendored_or_build"
    if any(pat.search(part) for part in parts for pat in SECRET_NAME_PATTERNS):
        return "secret_file"
    if any(pat.search(part) for part in parts for pat in MACHINE_LOCAL_PATTERNS):
        return "machine_local"
    return None


def classify_path(rel_path, mode):
    """Classify a non-excluded tracked path into an inventory bucket, or None."""
    parts = rel_path.split("/")
    if parts[0] == ".byte-stack":
        return None
    lower_path = rel_path.lower()
    lower_name = parts[-1].lower()
    suffix = Path(lower_name).suffix

    if (
        (len(parts) >= 3 and parts[0] == ".github" and parts[1] == "workflows" and suffix in (".yml", ".yaml"))
        or lower_path in CI_PATHS
        or (len(parts) >= 2 and parts[0] == ".buildkite" and suffix in (".yml", ".yaml"))
    ):
        return "ci"
    if (
        lower_path in HOOK_PATHS
        or (parts[0] == ".husky" and len(parts) == 2 and not lower_name.startswith("_"))
        or (parts[0] in (".githooks", "githooks") and len(parts) >= 2)
        or lower_name.startswith((".lintstagedrc", "lint-staged.config."))
    ):
        return "git_hooks"
    if (
        lower_name in STEERING_NAMES
        or lower_path in (".github/copilot-instructions.md", ".cursorrules")
        or lower_path.startswith(".cursor/rules/")
    ):
        return "steering"
    if suffix in (".md", ".mdx") and lower_path.startswith(("docs/adr/", "docs/adrs/", "docs/decisions/", "adr/", "adrs/")):
        return "adrs"
    if (
        (lower_path.startswith(("docs/directives/", "docs/standards/", "docs/guidelines/", "docs/policies/"))
         and suffix in (".md", ".mdx", ".txt"))
        or lower_name in DIRECTIVE_NAMES
        or lower_path in DIRECTIVE_PATHS
    ):
        return "directives"
    if (
        lower_name in QUALITY_EXACT_NAMES
        or any(lower_name.startswith(pref) for pref in QUALITY_PREFIXES)
        or lower_path in (".github/dependabot.yml", ".github/dependabot.yaml")
    ):
        return "quality"
    if lower_name in TASK_RUNNER_NAMES or suffix == ".mk" or lower_name.startswith(("gruntfile.", "gulpfile.")):
        return "task_runners"
    if parts[0] in SCRIPT_DIRS and (suffix in SCRIPT_EXTS or mode == "100755"):
        return "scripts"
    return None


def _extract_script_summary(lines):
    """Return (1-based line_no, text) for the first leading comment or docstring line."""
    end_delim = None
    for idx, line in enumerate(lines, 1):
        s = line.strip()
        if not s or (idx == 1 and s.startswith("#!")):
            continue
        if end_delim is not None:
            if end_delim in s:
                body = s.split(end_delim, 1)[0].lstrip("* ").strip()
                end_delim = None
                if body:
                    return idx, body
                continue
            body = s.lstrip("* ").strip() if end_delim == "*/" else s
            if body:
                return idx, body
            continue
        for start, end in (('"""', '"""'), ("'''", "'''"), ("/*", "*/")):
            if s.startswith(start):
                rest = s[len(start):]
                if end in rest:
                    body = rest.split(end, 1)[0].lstrip("* ").strip()
                    if body:
                        return idx, body
                else:
                    body = rest.lstrip("* ").strip() if end == "*/" else rest.strip()
                    if body:
                        return idx, body
                    end_delim = end
                break
        else:
            if s.startswith(("#", "//")):
                body = s.lstrip("#/").strip()
                if body and not (set(body) <= {"-", "=", "*"}):
                    return idx, body
                continue
            break
    return None


def extract_signals(rel_path, text, bmode_capture, repo_strings, bucket=None):
    """Extract bounded signals (commands, keys, headings, or one script summary) with line numbers."""
    signals, truncated_signals, dropped_sensitive = [], False, 0
    lines = text.splitlines()
    lower_name = Path(rel_path).name.lower()
    suffix = Path(lower_name).suffix

    def add_signal(kind, line_no, raw_text, key_name=None):
        nonlocal truncated_signals, dropped_sensitive
        if _contains_sensitive(raw_text, bmode_capture, repo_strings) or (
            key_name is not None and _contains_sensitive(key_name, bmode_capture, repo_strings)
        ):
            dropped_sensitive += 1
            return
        collapsed = " ".join(raw_text.strip().split())
        if not collapsed:
            return
        if len(collapsed) > MAX_SIGNAL_TEXT_LEN:
            collapsed = collapsed[: MAX_SIGNAL_TEXT_LEN - 3] + "..."
        if len(signals) >= MAX_SIGNALS_PER_FILE:
            truncated_signals = True
            return
        sig = {"kind": kind, "line": line_no, "text": collapsed}
        if key_name is not None:
            sig["key"] = key_name
        signals.append(sig)

    if bucket == "scripts":
        summary = _extract_script_summary(lines)
        if summary is not None:
            add_signal("summary", summary[0], summary[1])
        return signals, False, dropped_sensitive

    if suffix in (".md", ".mdx"):
        in_fence, fence_shell = False, False
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("```"):
                if not in_fence:
                    lang = stripped[3:].strip().lower().split()[0] if stripped[3:].strip() else ""
                    in_fence, fence_shell = True, lang in ("sh", "bash", "shell", "zsh", "console", "")
                else:
                    in_fence, fence_shell = False, False
            elif not in_fence and re.match(r"^#{1,4}\s+\S", stripped):
                add_signal("heading", idx, stripped)
            elif in_fence and fence_shell and stripped and not stripped.startswith("#"):
                add_signal("command", idx, stripped[2:].strip() if stripped.startswith("$ ") else stripped)
    elif suffix in (".json", ".jsonc"):
        parsed = None
        if lower_name == "package.json":
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
        if isinstance(parsed, dict):
            scripts_obj = parsed.get("scripts")
            if isinstance(scripts_obj, dict):
                for sname in sorted(scripts_obj):
                    if isinstance(scripts_obj[sname], str):
                        ln = next((i for i, l in enumerate(lines, 1) if f'"{sname}"' in l), 1)
                        add_signal("command", ln, scripts_obj[sname], key_name=f"scripts.{sname}")
            for k in sorted(parsed):
                if k != "scripts":
                    ln = next((i for i, l in enumerate(lines, 1) if f'"{k}"' in l), 1)
                    add_signal("key", ln, k)
        else:
            for idx, line in enumerate(lines, 1):
                m = re.match(r'^\s{1,2}"([^"]+)"\s*:', line)
                if m:
                    add_signal("key", idx, m.group(1))
    elif suffix in (".yml", ".yaml"):
        in_run_block, run_indent = False, 0
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            if in_run_block:
                if indent > run_indent:
                    add_signal("command", idx, stripped)
                    continue
                in_run_block = False
            m_run = re.match(r"^(\s*)(?:-\s*)?run:\s*(.*)$", line)
            if m_run:
                val = m_run.group(2).strip()
                if val in ("|", ">", "|-", ">-", "|+", ">+"):
                    in_run_block, run_indent = True, indent
                elif val:
                    add_signal("command", idx, val)
                continue
            m_uses = re.match(r"^\s*(?:-\s*)?(?:uses|repo|id):\s*(.+)$", line)
            if m_uses:
                add_signal("key", idx, m_uses.group(0).strip())
            elif indent == 0:
                m_top = re.match(r"^([A-Za-z0-9_.-]+):", line)
                if m_top:
                    add_signal("key", idx, m_top.group(1))
    elif lower_name in ("makefile", "gnumakefile", "justfile") or suffix == ".mk":
        for idx, line in enumerate(lines, 1):
            if line.startswith("\t"):
                cmd = line.strip()
                if cmd and not cmd.startswith("#"):
                    add_signal("command", idx, cmd.lstrip("@-").strip())
                continue
            m_target = re.match(r"^([A-Za-z0-9_./-]+)\s*:(?!=)", line)
            if m_target and not m_target.group(1).startswith("."):
                add_signal("key", idx, m_target.group(1))
    elif suffix in (".toml", ".ini", ".cfg") or lower_name in (".editorconfig", ".flake8"):
        current_sec, in_scripts = "", False
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";")):
                continue
            m_sec = re.match(r"^\[([^\]]+)\]$", stripped)
            if m_sec:
                current_sec = m_sec.group(1).strip()
                add_signal("key", idx, current_sec)
                in_scripts = current_sec.endswith("scripts")
            elif "=" in stripped:
                k, v = (part.strip() for part in stripped.split("=", 1))
                if in_scripts:
                    cmd_val = v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'") else v
                    add_signal("command", idx, cmd_val, key_name=f"{current_sec}.{k}" if current_sec else k)
                elif not line.startswith((" ", "\t")):
                    add_signal("key", idx, k)
    else:
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if idx == 1 and stripped.startswith("#!"):
                add_signal("heading", idx, stripped)
            elif re.match(r"^(?:def|async def|function|export function)\s+[A-Za-z0-9_-]+", stripped):
                add_signal("key", idx, stripped.split("{")[0].rstrip(":"))
            elif re.match(r"^(?:python3?|node|npm|pnpm|yarn|pytest|go|cargo|git|make|bash|sh|rg)\s+\S", stripped):
                add_signal("command", idx, stripped)

    return signals, truncated_signals, dropped_sensitive


def _normalize_lf(text):
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized + "\n" if normalized and not normalized.endswith("\n") else normalized


def _normalize_title_or_trigger(text):
    return " ".join(text.split()).lower().rstrip(".:")


def _extract_h1(text):
    return next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "")


def _tokenize(text):
    return {w for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if w not in STOPWORDS}


def _catalog_tokens(kind, title, trigger):
    if kind in ("playbooks", "workflows"):
        return _tokenize(f"{title} {trigger}")
    return _tokenize(title) if kind == "references" else frozenset()


def _inspect_markdown_head(text, path_label, bmode_assets):
    """Parse frontmatter, trigger, and H1 title from a bounded Markdown head."""
    if not text.strip():
        raise ValueError(f"empty asset: {path_label}")
    meta, body = bmode_assets.parse_frontmatter(text, path_label)
    if not body.strip():
        raise ValueError(f"empty asset: {path_label}")
    fm_trigger = meta.get("use-when", "").strip()
    body_trigger = next(
        (line.removeprefix("Use when: ").strip() for line in body.splitlines() if line.startswith("Use when: ")),
        "",
    )
    if fm_trigger and body_trigger and fm_trigger != body_trigger:
        raise ValueError(f"conflicting trigger descriptions: {path_label}")
    return fm_trigger or body_trigger, _extract_h1(body)


def read_bundled_catalog(bmode_assets, bmode_dir):
    """Enumerate bundled bmode assets across all four kinds once."""
    by_kind = {}
    for kind in bmode_assets.KINDS:
        entries = {}
        base = bmode_dir / kind
        if base.is_dir():
            for path in sorted(base.rglob("*")):
                rel = path.relative_to(base)
                if any(p.startswith(".") or p == "__pycache__" for p in rel.parts):
                    continue
                if path.is_dir() or (kind in ("playbooks", "workflows") and path.suffix != ".md"):
                    continue
                key = rel.as_posix()
                trigger = bmode_assets.inspect_file(path, kind)
                raw = path.read_bytes() if path.stat().st_size <= MAX_CONTENT_BYTES else None
                sha = hashlib.sha256(raw).hexdigest() if raw is not None else None
                title = ""
                if path.suffix == ".md":
                    txt = raw.decode("utf-8", errors="replace") if raw is not None else path.read_text(encoding="utf-8", errors="replace")
                    title = _extract_h1(txt)
                entries[key] = {
                    "origin": "bundled", "kind": kind, "key": key, "trigger": trigger,
                    "title": title, "content_sha256": sha, "tokens": _catalog_tokens(kind, title, trigger),
                }
        by_kind[kind] = entries
    return by_kind


def _walk_repo_kind_dir(r_base, kind, on_excl=None, on_error=None):
    """Yield (rel_posix, path, lstat) under .byte-stack/<kind>/ safely without following symlinks."""
    def recurse(cur_dir):
        try:
            children = sorted(cur_dir.iterdir(), key=lambda p: p.name)
        except OSError as err:
            if on_error:
                on_error(err)
            return
        for child in children:
            rel_parts = child.relative_to(r_base).parts
            rel_posix = "/".join(rel_parts)
            if child.is_symlink():
                err = ValueError(f"symlink in asset path: {child}")
                if on_error:
                    on_error(err)
                    continue
                raise err
            try:
                st = child.lstat()
            except OSError as err:
                if on_error:
                    on_error(err)
                    continue
                raise
            is_dir = stat.S_ISDIR(st.st_mode)
            excl = exclusion_reason(f"{rel_posix}/_" if is_dir else rel_posix, "100644")
            if excl is not None:
                if on_excl:
                    on_excl(f".byte-stack/{kind}/{rel_posix}", excl)
                continue
            if any(p.startswith(".") or p == "__pycache__" for p in rel_parts):
                continue
            if is_dir:
                yield from recurse(child)
                continue
            if kind in ("playbooks", "workflows") and child.suffix != ".md":
                continue
            if not stat.S_ISREG(st.st_mode):
                err = ValueError(f"expected regular file: {child}")
                if on_error:
                    on_error(err)
                    continue
                raise err
            yield rel_posix, child, st

    yield from recurse(r_base)


def collect_byte_stack_inventory(repo, bmode_dir, bmode_assets, bmode_capture, budget, excluded_paths):
    """Inspect bundled and repo .byte-stack catalogs with exclusions, shared budget, and redaction."""
    bundled_all = read_bundled_catalog(bmode_assets, bmode_dir)
    catalog_out, diagnostics = {}, []

    def add_diag(kind, message):
        diagnostics.append({
            "kind": kind,
            "message": _sanitize_text(str(message), repo, bmode_dir, bmode_capture),
            "scope": "byte_stack",
        })

    def note_excl(repo_rel, reason):
        if repo_rel not in excluded_paths:
            excluded_paths.add(repo_rel)
            budget["bump"](reason)

    for kind in bmode_assets.KINDS:
        bundled, repo_items = bundled_all[kind], {}
        try:
            r_base = bmode_assets.checked(repo, [".byte-stack", kind])
            if r_base.exists() and not r_base.is_dir():
                raise ValueError(f"expected directory: {r_base}")
        except (OSError, ValueError) as err:
            add_diag(kind, err)
            r_base = None

        if r_base is not None and r_base.exists():
            for key, path, st in _walk_repo_kind_dir(
                r_base, kind, on_excl=note_excl, on_error=lambda err, k=kind: add_diag(k, err)
            ):
                if budget["files_read"] >= budget["max_files"]:
                    budget["truncated"]["files"] = True
                    budget["bump"]("max_files_limit")
                    continue
                if budget["bytes_remaining"] <= 0:
                    budget["truncated"]["bytes"] = True
                    budget["bump"]("max_bytes_limit")
                    continue
                try:
                    if kind != "scripts" and path.suffix == ".md":
                        read_cap = min(CATALOG_HEAD_BYTES, budget["bytes_remaining"])
                        with path.open("rb") as handle:
                            raw = handle.read(read_cap)
                        budget["files_read"] += 1
                        budget["bytes_remaining"] -= len(raw)
                        if len(raw) < st.st_size and read_cap < CATALOG_HEAD_BYTES:
                            budget["truncated"]["bytes"] = True
                        if b"\x00" in raw:
                            budget["bump"]("binary")
                            continue
                        trigger, _ = _inspect_markdown_head(raw.decode("utf-8", errors="replace"), path, bmode_assets)
                        if kind == "playbooks" and not trigger:
                            trigger = bundled[key]["trigger"] if key in bundled else ""
                            if not trigger:
                                suffix_msg = f" within first {len(raw)} bytes" if len(raw) < st.st_size else ""
                                add_diag(kind, f"missing 'Use when: ' description{suffix_msg}: {path}")
                                continue
                    else:
                        with path.open("rb"):
                            pass
                        budget["files_read"] += 1
                        trigger = ""
                except (OSError, ValueError) as err:
                    add_diag(kind, err)
                    continue

                repo_items[key] = {
                    "key": _sanitize_text(key, repo, bmode_dir, bmode_capture),
                    "origin": "repo",
                    "overrides_bundled": key in bundled,
                    "repo_path": _sanitize_text(f".byte-stack/{kind}/{key}", repo, bmode_dir, bmode_capture),
                    "trigger": _sanitize_text(trigger, repo, bmode_dir, bmode_capture),
                }

        catalog_out[kind] = [
            repo_items[k] if k in repo_items else {
                "key": bundled[k]["key"], "origin": "bundled",
                "overrides_bundled": False, "trigger": bundled[k]["trigger"],
            }
            for k in sorted(set(bundled) | set(repo_items))
        ]

    diagnostics.sort(key=lambda d: (d["scope"], d["kind"], d["message"]))
    return catalog_out, diagnostics


def cmd_inventory(args):
    if args.max_files < 1 or args.max_bytes < 1:
        print("--max-files and --max-bytes must be positive integers", file=sys.stderr)
        return 1

    bmode_dir = bmode_capture = repo = None
    try:
        bmode_dir, bmode_assets, bmode_capture, _ = load_bmode(args.bmode)
        repo = bmode_assets.checkout(args.cwd)
        if repo is None:
            raise DiagnosticError("Run extract-assets inside a Git worktree.")
        tracked = list_tracked_files(repo)
    except (DiagnosticError, OSError, ValueError) as err:
        print(_sanitize_text(str(err), repo, bmode_dir, bmode_capture, extra_paths=(args.cwd,)), file=sys.stderr)
        return 2

    repo_strs = tuple(sorted({str(repo), str(repo.resolve())}, key=len, reverse=True))
    categories = {k: [] for k in ("adrs", "ci", "directives", "git_hooks", "quality", "scripts", "steering", "task_runners")}
    exclusions, excluded_paths, unclassified_count = {}, set(), 0
    truncated = {"bytes": False, "files": False, "signals": False}

    def bump_exclusion(reason, count=1):
        if count > 0:
            exclusions[reason] = exclusions.get(reason, 0) + count

    budget = {
        "files_read": 0, "bytes_remaining": args.max_bytes,
        "max_files": args.max_files, "truncated": truncated, "bump": bump_exclusion,
    }

    for rel_path, mode in tracked:
        reason = exclusion_reason(rel_path, mode)
        if reason is not None:
            excluded_paths.add(rel_path)
            bump_exclusion(reason)
            continue
        bucket = classify_path(rel_path, mode)
        if bucket is None:
            if not rel_path.startswith(".byte-stack/"):
                unclassified_count += 1
            continue
        if budget["files_read"] >= args.max_files:
            truncated["files"] = True
            bump_exclusion("max_files_limit")
            continue
        if budget["bytes_remaining"] <= 0:
            truncated["bytes"] = True
            bump_exclusion("max_bytes_limit")
            continue

        try:
            target = bmode_assets.checked(repo, rel_path.split("/"))
        except ValueError:
            bump_exclusion("symlink")
            continue
        if not target.exists():
            bump_exclusion("missing_in_worktree")
            continue
        try:
            st = target.lstat()
            if not stat.S_ISREG(st.st_mode):
                bump_exclusion("non_regular_file")
                continue
            with target.open("rb") as handle:
                raw = handle.read(budget["bytes_remaining"])
        except OSError:
            bump_exclusion("unreadable")
            continue

        budget["files_read"] += 1
        bytes_read = len(raw)
        budget["bytes_remaining"] -= bytes_read
        file_truncated = bytes_read < st.st_size
        if file_truncated:
            truncated["bytes"] = True
        if b"\x00" in raw:
            bump_exclusion("binary")
            continue

        text = raw.decode("utf-8", errors="replace")
        signals, sig_truncated, dropped = extract_signals(rel_path, text, bmode_capture, repo_strs, bucket=bucket)
        if sig_truncated:
            file_truncated = truncated["signals"] = True
        bump_exclusion("sensitive_signals_dropped", dropped)
        categories[bucket].append({
            "bytes": st.st_size, "bytes_read": bytes_read, "lines": len(text.splitlines()),
            "path": rel_path, "signals": signals, "truncated": file_truncated,
        })

    for bucket in categories:
        categories[bucket].sort(key=lambda item: item["path"])

    byte_stack_catalog, diagnostics = collect_byte_stack_inventory(
        repo, bmode_dir, bmode_assets, bmode_capture, budget, excluded_paths
    )
    output = {
        "byte_stack": byte_stack_catalog,
        "categories": categories,
        "diagnostics": diagnostics,
        "exclusions": dict(sorted(exclusions.items())),
        "limits": {"max_bytes": args.max_bytes, "max_files": args.max_files, "max_signals_per_file": MAX_SIGNALS_PER_FILE},
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "bytes_read": args.max_bytes - budget["bytes_remaining"],
            "files_read": budget["files_read"],
            "tracked_files": len(tracked),
            "unclassified_tracked_files": unclassified_count,
        },
        "truncated": truncated,
    }
    print(json.dumps(output, indent=2, sort_keys=True) if args.pretty else json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


def _token_pattern(needle):
    tokens = needle.split()
    if not tokens:
        return None
    body = r"\s+".join(re.escape(tok) for tok in tokens)
    prefix = r"(?<![A-Za-z0-9_-])" if _TOKEN_CHAR_RE.match(tokens[0][0]) else ""
    suffix = r"(?![A-Za-z0-9_-])" if _TOKEN_CHAR_RE.match(tokens[-1][-1]) else ""
    return re.compile(prefix + body + suffix)


def _line_command_window(file_lines, line_no, cmd):
    """Build logical command text at 1-based line_no, handling \\ continuations and multi-line commands."""
    idx, min_lines, parts, consumed = line_no - 1, max(1, len(cmd.splitlines())), [], 0
    while idx < len(file_lines):
        line = file_lines[idx]
        idx += 1
        consumed += 1
        if line.rstrip().endswith("\\") and idx < len(file_lines):
            parts.append(line.rstrip()[:-1])
            continue
        parts.append(line)
        if consumed >= min_lines:
            break
    return " ".join(parts)


def _validate_rendered_reference(key_hint, norm_content, bmode_assets):
    """Run assets.inspect_file on a candidate reference in an out-of-repo temp dir."""
    suffix = ".md" if (not isinstance(key_hint, str) or key_hint.endswith(".md")) else Path(key_hint).suffix
    with tempfile.TemporaryDirectory(prefix="extract-preflight-") as tmp_dir:
        tmp_file = Path(tmp_dir) / f"candidate{suffix}"
        tmp_file.write_bytes(norm_content.encode("utf-8"))
        bmode_assets.inspect_file(tmp_file, "references")


def _candidate_lines_for_steering(candidate):
    if candidate["kind"] in ("playbooks", "workflows"):
        p = candidate["payload"]
        raw_items = [p.get("title", ""), p.get("use_when", "")]
        for field in ("prerequisites", "steps", "verification", "guardrails"):
            raw_items.extend(p.get(field, []))
        return [item.strip() for item in raw_items if item and item.strip()]
    return [line.strip() for line in _normalize_lf(candidate["content"]).splitlines() if line.strip() and line.strip() != "---"]


def _check_payload_strings(prefix, payload, bmode_capture, errors):
    """Validate UTF-8 and bare machine-local paths across payload string fields."""
    utf8_ok = True
    checks = []
    for field in ("title", "use_when"):
        if isinstance(payload.get(field), str):
            checks.append((field, payload[field]))
    for field in ("prerequisites", "steps", "verification", "guardrails"):
        items = payload.get(field)
        if isinstance(items, list):
            for iidx, item in enumerate(items):
                if isinstance(item, str):
                    checks.append((f"{field}[{iidx}]", item))
    for label, val in checks:
        if not _check_utf8(f"{prefix}.payload.{label}", val, errors):
            utf8_ok = False
        elif any(p.search(val) for p in EXTRA_LOCAL_PATH_PATTERNS) and not any(
            p.search(val) for p in bmode_capture.LOCAL_PATH_PATTERNS
        ):
            errors.append(f"{prefix}.payload: {label} must not contain a machine-local home path")
    return utf8_ok


def validate_candidates_envelope(data, repo, bmode_dir, tracked_map, bmode_assets, bmode_capture):
    """Validate candidate envelope, per-kind rules, UTF-8, safety patterns, and provenance."""
    if not isinstance(data, dict):
        return ["candidates input must be a JSON object"]
    errors = []
    unknown_env = sorted(set(data) - ALLOWED_ENVELOPE_KEYS)
    if unknown_env:
        errors.append(f"unknown envelope field(s): {', '.join(unknown_env)}")
    if "schema_version" not in data:
        errors.append("missing required field: schema_version")
    elif isinstance(data["schema_version"], bool) or data["schema_version"] != SCHEMA_VERSION:
        errors.append(f"schema_version must be integer {SCHEMA_VERSION}")
    if "candidates" not in data:
        return errors + ["missing required field: candidates"]
    candidates = data["candidates"]
    if not isinstance(candidates, list):
        return errors + ["candidates must be an array"]
    if len(candidates) > 50:
        errors.append("candidates must contain at most 50 items")

    seen_ids, file_cache = set(), {}

    def read_provenance_file(rel_path):
        if rel_path not in file_cache:
            target = bmode_assets.checked(repo, rel_path.split("/"))
            _check_regular(target)
            if not target.exists():
                raise ValueError(f"missing file in worktree: {rel_path}")
            with target.open("rb") as handle:
                text = handle.read(MAX_PROVENANCE_READ_BYTES).decode("utf-8", errors="replace")
            file_cache[rel_path] = (text, text.splitlines(), re.sub(r"\\\r?\n", " ", text))
        return file_cache[rel_path]

    for idx, cand in enumerate(candidates):
        prefix = f"candidates[{idx}]"
        if not isinstance(cand, dict):
            errors.append(f"{prefix} must be an object")
            continue
        unknown_c = sorted(set(cand) - ALLOWED_CANDIDATE_KEYS)
        if unknown_c:
            errors.append(f"{prefix} has unknown field(s): {', '.join(unknown_c)}")
        for req in ("id", "category", "kind", "key", "provenance"):
            if req not in cand:
                errors.append(f"{prefix} missing required field: {req}")

        category = cand.get("category")
        if "category" in cand and (
            not isinstance(category, str)
            or (_check_utf8(f"{prefix}.category", category, errors) and category not in ALLOWED_CATEGORIES)
        ):
            errors.append(f"{prefix}.category must be one of: {', '.join(ALLOWED_CATEGORIES)}")

        kind = cand.get("kind")
        valid_kind = False
        if "kind" in cand:
            if not isinstance(kind, str):
                errors.append(f"{prefix}.kind must be one of: {', '.join(ALLOWED_KINDS)}")
            elif _check_utf8(f"{prefix}.kind", kind, errors):
                if kind in ALLOWED_KINDS:
                    valid_kind = True
                else:
                    errors.append(f"{prefix}.kind must be one of: {', '.join(ALLOWED_KINDS)}")

        key, valid_str_key = cand.get("key"), False
        if "key" in cand:
            if not isinstance(key, str):
                errors.append(f"{prefix}.key must be a string")
            elif _check_utf8(f"{prefix}.key", key, errors):
                valid_str_key = True
                _check_safety_patterns(bmode_capture, f"{prefix}.key", key, errors)
                if valid_kind:
                    try:
                        bmode_assets.validate_key(kind, key)
                    except ValueError as err:
                        errors.append(f"{prefix}.key: {err}")
                    if kind in ("playbooks", "workflows") and (not (4 <= len(key) <= 120) or not bmode_capture.KEY_PATTERN.fullmatch(key)):
                        errors.append(f"{prefix}.key must be lowercase kebab-case path ending in .md (4..120 chars)")
                    elif kind == "references" and (not (4 <= len(key) <= 120) or not REF_KEY_PATTERN.fullmatch(key)):
                        errors.append(f"{prefix}.key must be lowercase kebab-case path ending in .md (4..120 chars)")
                    elif kind == "scripts" and (not (2 <= len(key) <= 120) or not SCRIPT_KEY_PATTERN.fullmatch(key)):
                        errors.append(f"{prefix}.key must be lowercase path (2..120 chars, alphanumeric/-/_ with optional extension)")

        cid = cand.get("id")
        if "id" in cand:
            if not isinstance(cid, str) or not cid.strip():
                errors.append(f"{prefix}.id must be a non-empty string")
            elif _check_utf8(f"{prefix}.id", cid, errors):
                if valid_kind and valid_str_key and cid != f"{kind}/{key}":
                    errors.append(f"{prefix}.id must equal '{kind}/{key}'")
                if cid in seen_ids:
                    errors.append(f"duplicate candidate id: {cid}")
                seen_ids.add(cid)

        if "rationale" in cand:
            rat = cand["rationale"]
            if not isinstance(rat, str) or not (3 <= len(rat.strip()) <= 400):
                errors.append(f"{prefix}.rationale must be a string (3..400 chars)")
            elif _check_utf8(f"{prefix}.rationale", rat, errors):
                _check_safety_patterns(bmode_capture, f"{prefix}.rationale", rat, errors)

        if "executable" in cand:
            if not isinstance(cand["executable"], bool):
                errors.append(f"{prefix}.executable must be a boolean")
            elif valid_kind and kind != "scripts":
                errors.append(f"{prefix}.executable is only allowed when kind is 'scripts'")

        prov_list = cand.get("provenance")
        if "provenance" in cand:
            if not isinstance(prov_list, list) or not (1 <= len(prov_list) <= 20):
                errors.append(f"{prefix}.provenance must be a non-empty array (1..20 items)")
            else:
                for pidx, prov in enumerate(prov_list):
                    pl = f"{prefix}.provenance[{pidx}]"
                    if not isinstance(prov, dict):
                        errors.append(f"{pl} must be an object")
                        continue
                    unknown_p = sorted(set(prov) - ALLOWED_PROVENANCE_KEYS)
                    if unknown_p:
                        errors.append(f"{pl} has unknown field(s): {', '.join(unknown_p)}")
                    ppath = prov.get("path")
                    if not isinstance(ppath, str) or not ppath.strip():
                        errors.append(f"{pl}.path must be a non-empty string")
                        continue
                    if not _check_utf8(f"{pl}.path", ppath, errors):
                        continue
                    _check_safety_patterns(bmode_capture, f"{pl}.path", ppath, errors)
                    if ppath.startswith("/") or "\\" in ppath or ".." in ppath.split("/"):
                        errors.append(f"{pl}.path must be a repo-relative POSIX path")
                        continue
                    if ppath not in tracked_map:
                        errors.append(f"{pl}.path is not a tracked repository file: {ppath}")
                        continue
                    excl = exclusion_reason(ppath, tracked_map[ppath])
                    if excl is not None:
                        errors.append(f"{pl}.path is excluded ({excl}): {ppath}")
                        continue
                    try:
                        file_text, file_lines, joined_text = read_provenance_file(ppath)
                    except (OSError, ValueError) as err:
                        errors.append(f"{pl}.path unreadable or unsafe: {_sanitize_text(str(err), repo, bmode_dir, bmode_capture)}")
                        continue

                    valid_line = None
                    if "line" in prov:
                        line_no = prov["line"]
                        if isinstance(line_no, bool) or not isinstance(line_no, int) or line_no < 1:
                            errors.append(f"{pl}.line must be a positive integer")
                        elif line_no > len(file_lines):
                            errors.append(f"{pl}.line {line_no} exceeds {ppath} length ({len(file_lines)} lines)")
                        else:
                            valid_line = line_no

                    if "command" in prov:
                        cmd = prov["command"]
                        if not isinstance(cmd, str) or not cmd.strip() or len(cmd) > 400:
                            errors.append(f"{pl}.command must be a non-empty string (<= 400 chars)")
                        elif _check_utf8(f"{pl}.command", cmd, errors):
                            _check_safety_patterns(bmode_capture, f"{pl}.command", cmd, errors)
                            pat = _token_pattern(cmd)
                            if valid_line is not None:
                                if not pat or not pat.search(_line_command_window(file_lines, valid_line, cmd)):
                                    errors.append(f"{pl}.command not found at line {valid_line} in {ppath}")
                            elif "line" not in prov and (not pat or not pat.search(joined_text)):
                                errors.append(f"{pl}.command not found in {ppath}")

                    if "key" in prov:
                        pkey = prov["key"]
                        if not isinstance(pkey, str) or not pkey.strip() or len(pkey) > 200:
                            errors.append(f"{pl}.key must be a non-empty string (<= 200 chars)")
                        elif _check_utf8(f"{pl}.key", pkey, errors):
                            _check_safety_patterns(bmode_capture, f"{pl}.key", pkey, errors)
                            segments = pkey.split(".")
                            if any(not seg.strip() for seg in segments):
                                errors.append(f"{pl}.key contains empty dotted segment: {pkey}")
                            else:
                                scope = "\n".join(file_lines[:valid_line]) if valid_line is not None else file_text
                                missing = [s for s in segments if not _token_pattern(s).search(scope)]
                                if missing:
                                    errors.append(f"{pl}.key segment(s) not found in {ppath}: {', '.join(missing)}")
                                elif valid_line is not None and not _token_pattern(segments[-1]).search(file_lines[valid_line - 1]):
                                    errors.append(f"{pl}.key leaf '{segments[-1]}' not found at line {valid_line} in {ppath}")

        if valid_kind and kind in ("playbooks", "workflows"):
            if "content" in cand:
                errors.append(f"{prefix}.content is not allowed for {kind}; use payload")
            if "payload" not in cand:
                errors.append(f"{prefix}.payload is required for {kind}")
            elif not isinstance(cand["payload"], dict):
                errors.append(f"{prefix}.payload must be an object")
            else:
                payload = cand["payload"]
                unknown_pl = sorted(set(payload) - ALLOWED_PAYLOAD_SUBKEYS)
                if unknown_pl:
                    errors.append(f"{prefix}.payload has unknown field(s): {', '.join(unknown_pl)}")
                elif _check_payload_strings(prefix, payload, bmode_capture, errors):
                    full_payload = {
                        "schema_version": SCHEMA_VERSION, "kind": kind,
                        "key": key if valid_str_key else "placeholder.md", **payload,
                    }
                    for perr in bmode_capture.validate_payload(full_payload):
                        if valid_str_key or not perr.startswith("key"):
                            errors.append(f"{prefix}.payload: {perr}")
        elif valid_kind and kind in ("references", "scripts"):
            if "payload" in cand:
                errors.append(f"{prefix}.payload is not allowed for {kind}; use content")
            if "content" not in cand:
                errors.append(f"{prefix}.content is required for {kind}")
            elif not isinstance(cand["content"], str) or not cand["content"].strip():
                errors.append(f"{prefix}.content must be a non-empty string")
            elif _check_utf8(f"{prefix}.content", cand["content"], errors):
                norm_content = _normalize_lf(cand["content"])
                if len(norm_content.encode("utf-8")) > MAX_CONTENT_BYTES:
                    errors.append(f"{prefix}.content exceeds {MAX_CONTENT_BYTES} bytes")
                _check_safety_patterns(bmode_capture, f"{prefix}.content", norm_content, errors)
                if kind == "references":
                    try:
                        _validate_rendered_reference(key if valid_str_key else "candidate.md", norm_content, bmode_assets)
                    except ValueError as err:
                        clean = re.sub(r":\s*/[^\s]+candidate\.md", "", str(err))
                        errors.append(f"{prefix}.content invalid reference: {clean}")

    return errors


def build_dedupe_context(repo, tracked_map, bmode_dir, bmode_assets):
    """Collect bundled entries, repo .byte-stack entries, and steering lines/tokens."""
    bundled_by_kind = read_bundled_catalog(bmode_assets, bmode_dir)
    catalog_entries = [entry for entries in bundled_by_kind.values() for entry in entries.values()]

    for kind in bmode_assets.KINDS:
        r_base = bmode_assets.checked(repo, [".byte-stack", kind])
        if not r_base.exists():
            continue
        if not r_base.is_dir():
            raise DiagnosticError(f"expected directory: {r_base}")
        for key, path, st in _walk_repo_kind_dir(r_base, kind):
            sha, trigger, title = None, "", ""
            if st.st_size <= MAX_CONTENT_BYTES:
                raw = path.read_bytes()
                sha, head = hashlib.sha256(raw).hexdigest(), raw[:CATALOG_HEAD_BYTES]
            else:
                with path.open("rb") as handle:
                    head = handle.read(CATALOG_HEAD_BYTES)
            if kind != "scripts" and path.suffix == ".md" and b"\x00" not in head:
                head_txt = head.decode("utf-8", errors="replace")
                try:
                    trigger, title = _inspect_markdown_head(head_txt, path, bmode_assets)
                except ValueError:
                    title = _extract_h1(head_txt)
            catalog_entries.append({
                "origin": "repo", "kind": kind, "key": key, "trigger": trigger,
                "title": title, "content_sha256": sha, "tokens": _catalog_tokens(kind, title, trigger),
            })

    steering_lines, steering_sources = set(), []
    for rel_path, mode in sorted(tracked_map.items()):
        if exclusion_reason(rel_path, mode) is not None or classify_path(rel_path, mode) != "steering":
            continue
        try:
            target = bmode_assets.checked(repo, rel_path.split("/"))
            _check_regular(target)
            if not target.exists():
                continue
            with target.open("rb") as handle:
                text = handle.read(MAX_PROVENANCE_READ_BYTES).decode("utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        unbulleted = set()
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if stripped:
                steering_lines.add(stripped)
                ub = re.sub(r"^(?:[-*+]|\d+\.)\s+", "", stripped).strip()
                if ub:
                    unbulleted.add(ub)
        steering_sources.append((rel_path, _tokenize(text), unbulleted))

    return {
        "bundled": bundled_by_kind, "catalog_entries": catalog_entries,
        "steering_lines": steering_lines, "steering_sources": steering_sources,
    }


def _token_similarity(tokens_a, tokens_b):
    if not tokens_a or not tokens_b:
        return 0, 0.0, 0.0
    shared = len(tokens_a & tokens_b)
    return shared, shared / len(tokens_a | tokens_b), shared / min(len(tokens_a), len(tokens_b))


def evaluate_dedupe(candidate, exists, is_identical, rendered_bytes, rendered_text, ctx):
    """Compute explicit dedupe verdict, reason, blocking flags, and scoped similar_to warnings."""
    kind, key, cid = candidate["kind"], candidate["key"], candidate["id"]
    flags, reasons = [], []

    if exists:
        flags.append("exists-identical" if is_identical else "exists-differs")
        reasons.append(f"existing .byte-stack/{kind}/{key} {'matches byte-for-byte' if is_identical else 'differs'}")
    elif key in ctx["bundled"].get(kind, {}):
        flags.append("overrides-bundled")
        reasons.append(f"overrides bundled byte-stack {kind}/{key} (pass --override-bundled {cid} to proceed)")

    prov_paths = [p["path"] for p in candidate["provenance"]]
    cand_lines = _candidate_lines_for_steering(candidate)
    matched_verbatim = sum(1 for line in cand_lines if line in ctx["steering_lines"]) if cand_lines else 0
    steering_ratio = (matched_verbatim / len(cand_lines)) if cand_lines else 0.0
    if prov_paths and all(classify_path(p, "100644") == "steering" for p in prov_paths):
        flags.append("restates-steering")
        reasons.append("all provenance cites standing steering files only")
    elif cand_lines and steering_ratio >= 0.80:
        flags.append("restates-steering")
        reasons.append(f"{matched_verbatim}/{len(cand_lines)} ({int(round(steering_ratio * 100))}%) of lines occur verbatim in steering files")

    cand_trigger = _normalize_title_or_trigger(candidate["payload"].get("use_when", "")) if kind in ("playbooks", "workflows") else ""
    cand_title = (
        _normalize_title_or_trigger(candidate["payload"].get("title", "")) if kind in ("playbooks", "workflows")
        else (_normalize_title_or_trigger(_extract_h1(rendered_text)) if kind == "references" and rendered_text else "")
    )
    cand_sha = hashlib.sha256(rendered_bytes).hexdigest() if rendered_bytes is not None else None

    for entry in ctx["catalog_entries"]:
        if entry["kind"] == kind and entry["key"] == key:
            continue
        if cand_sha is not None and entry["kind"] == kind and entry.get("content_sha256") == cand_sha:
            flags.append("duplicates-catalog")
            reasons.append(f"identical content to {entry['origin']} {entry['kind']}/{entry['key']}")
            break
        other_trigger = _normalize_title_or_trigger(entry["trigger"]) if entry["trigger"] else ""
        other_title = _normalize_title_or_trigger(entry["title"]) if entry["title"] else ""
        if (cand_trigger and cand_trigger == other_trigger) or (cand_title and cand_title == other_title):
            flags.append("duplicates-catalog")
            reasons.append(f"same trigger or title as {entry['origin']} {entry['kind']}/{entry['key']}")
            break

    verdict = next(
        (v for v in ("exists-identical", "exists-differs", "overrides-bundled", "restates-steering", "duplicates-catalog") if v in flags),
        "new",
    )
    if verdict == "new":
        reasons.append("no conflict with bundled catalog, existing .byte-stack/, or steering files")

    similar_scores = {}
    if kind != "scripts":
        cat_tokens = _catalog_tokens(kind, cand_title, cand_trigger)
        if cat_tokens:
            allowed_kinds = ("playbooks", "workflows") if kind in ("playbooks", "workflows") else ("references",)
            for entry in ctx["catalog_entries"]:
                if (entry["kind"] == kind and entry["key"] == key) or entry["kind"] not in allowed_kinds:
                    continue
                shared, jaccard, overlap = _token_similarity(cat_tokens, entry["tokens"])
                if (shared >= 3 and (jaccard >= 0.40 or overlap >= 0.50)) if kind in ("playbooks", "workflows") else (shared >= 2 and jaccard >= 0.50):
                    src = f"{entry['origin']}:{entry['kind']}/{entry['key']}"
                    similar_scores[src] = max(similar_scores.get(src, 0.0), round(max(jaccard, overlap), 2))
        body_tokens = _tokenize("\n".join(cand_lines))
        cand_ub = [re.sub(r"^(?:[-*+]|\d+\.)\s+", "", l).strip() for l in cand_lines]
        cand_ub = [l for l in cand_ub if l]
        for spath, stokens, sunbulleted in ctx["steering_sources"]:
            src = f"steering:{spath}"
            shared, jaccard, overlap = _token_similarity(body_tokens, stokens)
            if shared >= 4 and (jaccard >= 0.25 or overlap >= 0.30):
                similar_scores[src] = max(similar_scores.get(src, 0.0), round(max(jaccard, overlap), 2))
            if cand_ub and sunbulleted:
                matched_ub = sum(1 for l in cand_ub if l in sunbulleted)
                if matched_ub >= 2 and (matched_ub / len(cand_ub)) >= 0.50:
                    similar_scores[src] = max(similar_scores.get(src, 0.0), round(matched_ub / len(cand_ub), 2))

    similar = sorted(({"score": s, "source": k} for k, s in similar_scores.items()), key=lambda x: (-x["score"], x["source"]))
    return {"dedupe_flags": flags, "reason": "; ".join(reasons), "similar_to": similar[:3], "verdict": verdict}


def apply_atomic_write(repo, parts, kind, content, executable, expected_bytes, bmode_assets):
    """Write a references/ or scripts/ file atomically with pre-replace inspection and TOCTOU guard."""
    target = bmode_assets.checked(repo, [".byte-stack", kind, *parts])
    _check_regular(target)
    if expected_bytes is None and target.exists():
        raise TargetChangedError(f"target appeared after preflight: {target}")
    existing_mode = stat.S_IMODE(target.lstat().st_mode) if target.exists() else None
    target.parent.mkdir(parents=True, exist_ok=True)
    target = bmode_assets.checked(repo, [".byte-stack", kind, *parts])
    _check_regular(target)
    fd, tmp_name = tempfile.mkstemp(prefix=".extract-", suffix=f".tmp{target.suffix}", dir=target.parent)
    tmp_path, unlink_tmp = Path(tmp_name), True
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        umask = os.umask(0)
        os.umask(umask)
        if existing_mode is not None:
            mode = (existing_mode | 0o111) & ~umask if (kind == "scripts" and executable is True) else existing_mode
        else:
            mode = (0o777 if (kind == "scripts" and executable is True) else 0o666) & ~umask
        os.chmod(tmp_path, mode)
        bmode_assets.inspect_file(tmp_path, kind)
        if expected_bytes is None:
            try:
                os.link(tmp_path, target)
            except FileExistsError:
                if target.is_symlink():
                    raise ValueError(f"symlink in asset path: {target}")
                raise TargetChangedError(f"target appeared after preflight: {target}")
        else:
            _check_regular(target)
            if (target.read_bytes() if target.exists() else None) != expected_bytes:
                raise TargetChangedError(f"target modified after preflight: {target}")
            os.replace(tmp_path, target)
            unlink_tmp = False
    finally:
        if unlink_tmp:
            tmp_path.unlink(missing_ok=True)
    return target


def _run_capture_subprocess(capture_py, subcmd_args, stdin_text=None):
    return subprocess.run(
        [sys.executable, "-I", str(capture_py), *subcmd_args],
        input=stdin_text, capture_output=True, text=True,
    )


def _blocking_dedupe_reason(cid, flags, allow_override, allow_force):
    if "restates-steering" in flags and not allow_force:
        return f"candidate restates steering files; pass --force {cid} to write anyway"
    if "duplicates-catalog" in flags and not allow_force:
        return f"candidate duplicates an existing catalog entry; pass --force {cid} to write anyway"
    if "overrides-bundled" in flags and not (allow_override or allow_force):
        return f"candidate overrides bundled byte-stack asset; pass --override-bundled {cid} or --force {cid}"
    return None


def _unified_diff_redacted(existing_norm, rendered, target_rel, exists, repo, bmode_dir, bmode_capture):
    raw_diff = "".join(
        difflib.unified_diff(
            existing_norm.splitlines(keepends=True), rendered.splitlines(keepends=True),
            fromfile="/dev/null" if not exists else f"a/{target_rel}", tofile=f"b/{target_rel}",
        )
    )
    return _redact_diff(raw_diff, repo, bmode_dir, bmode_capture), raw_diff


def _plan_candidate(
    cand, repo, bmode_dir, bmode_assets, bmode_capture, capture_py, dedupe_ctx, update_ids, force_ids, override_ids
):
    """Dry-run one candidate, returning (exit_code, plan_dict, error_message)."""
    cid, kind, key = cand["id"], cand["kind"], cand["key"]
    parts = bmode_assets.validate_key(kind, key)
    target_rel = f".byte-stack/{kind}/{key}"
    allow_update, allow_force, allow_override = cid in update_ids, cid in force_ids, cid in override_ids

    base_plan = {
        "category": cand["category"], "id": cid, "key": key, "kind": kind,
        "provenance": cand["provenance"], "relative_path": target_rel,
    }

    if kind in ("playbooks", "workflows"):
        full_payload = {"schema_version": SCHEMA_VERSION, "kind": kind, "key": key, **cand["payload"]}
        cap_args = ["write", "--stdin", "--dry-run", "--json", "--cwd", str(repo)]
        if allow_update:
            cap_args.append("--update")
        if allow_force:
            cap_args.append("--force")
        proc = _run_capture_subprocess(capture_py, cap_args, stdin_text=json.dumps(full_payload))
        if proc.returncode in (1, 2):
            return proc.returncode, None, (proc.stderr.strip() or proc.stdout.strip())
        try:
            cap_res = json.loads(proc.stdout)
        except ValueError as err:
            return 2, None, f"capture_playbook.py returned non-JSON: {err}"

        status, plan_code = cap_res["status"], proc.returncode
        dedupe = evaluate_dedupe(cand, status != "create", status == "unchanged", None, None, dedupe_ctx)
        diff = _redact_diff(cap_res.get("diff", ""), repo, bmode_dir, bmode_capture)
        plan_reason = _sanitize_text(cap_res.get("reason", ""), repo, bmode_dir, bmode_capture)
        will_write = status in ("create", "update", "force-overwrite") and plan_code == 0
        if plan_code == 0 and status != "unchanged":
            blocking = _blocking_dedupe_reason(cid, dedupe["dedupe_flags"], allow_override, allow_force)
            if blocking is not None:
                status, plan_code, will_write, plan_reason = "conflict", 3, False, blocking
        return plan_code, {
            **base_plan, "dedupe_flags": dedupe["dedupe_flags"], "diff": diff,
            "full_payload": full_payload, "reason": plan_reason or dedupe["reason"],
            "similar_to": dedupe["similar_to"], "status": status,
            "title": cand["payload"].get("title", ""), "trigger": cand["payload"].get("use_when", ""),
            "verdict": dedupe["verdict"], "verdict_reason": dedupe["reason"], "will_write": will_write,
        }, None

    try:
        target = bmode_assets.checked(repo, [".byte-stack", kind, *parts])
        _check_regular(target)
        existing_bytes = target.read_bytes() if target.exists() else None
    except (OSError, ValueError) as err:
        return 2, None, str(err)

    rendered = _normalize_lf(cand["content"])
    rendered_bytes = rendered.encode("utf-8")
    exists, is_identical = existing_bytes is not None, existing_bytes == rendered_bytes
    dedupe = evaluate_dedupe(cand, exists, is_identical, rendered_bytes, rendered, dedupe_ctx)

    existing_norm = existing_bytes.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n") if exists else ""
    diff, raw_diff = _unified_diff_redacted(existing_norm, rendered, target_rel, exists, repo, bmode_dir, bmode_capture)
    line_endings_only = exists and not is_identical and existing_norm == rendered
    if exists and not is_identical and not raw_diff:
        note = "line endings differ (existing file uses CR/CRLF; candidate uses LF)" if line_endings_only else "file bytes differ"
        diff = f"--- a/{target_rel}\n+++ b/{target_rel}\n@@ {note} @@\n"

    verdict_reason = dedupe["reason"].replace("differs", "differs (line endings differ)", 1) if line_endings_only else dedupe["reason"]
    blocking = _blocking_dedupe_reason(cid, dedupe["dedupe_flags"], allow_override, allow_force)
    if not exists:
        status, plan_code, will_write, plan_reason = (
            ("conflict", 3, False, blocking) if blocking else ("create", 0, True, f"new {kind[:-1]}")
        )
    elif is_identical:
        status, plan_code, will_write, diff, plan_reason = "unchanged", 0, False, "", "already up to date"
    else:
        eol_note = " (line endings differ)" if line_endings_only else ""
        if allow_force and blocking is None:
            status, plan_code, will_write, plan_reason = "force-overwrite", 0, True, f"forced overwrite of existing {target_rel}{eol_note}"
        else:
            status, plan_code, will_write = "conflict", 3, False
            plan_reason = blocking or f"refusing to overwrite differing {target_rel}{eol_note} without --force {cid}"

    return plan_code, {
        **base_plan, "content_sha256": hashlib.sha256(rendered_bytes).hexdigest(),
        "dedupe_flags": dedupe["dedupe_flags"], "diff": diff, "executable": cand.get("executable", False),
        "expected_bytes": existing_bytes, "parts": parts, "reason": plan_reason, "rendered": rendered,
        "similar_to": dedupe["similar_to"], "status": status,
        "title": _extract_h1(rendered) if kind == "references" else "", "trigger": "",
        "verdict": dedupe["verdict"], "verdict_reason": verdict_reason, "will_write": will_write,
    }, None


def _emit_invalid(errors, as_json):
    if as_json:
        print(json.dumps({"errors": errors, "status": "invalid"}, indent=2, sort_keys=True))
    else:
        for err in errors:
            print(f"candidate error: {err}", file=sys.stderr)
    return 1


def _public_plan_item(plan, *, written=False, validated=None, resolved_origin=None):
    item = {k: plan[k] for k in PUBLIC_PLAN_KEYS}
    item["written"] = written
    if validated is not None:
        item["validated"] = validated
    if resolved_origin is not None:
        item["resolved_origin"] = resolved_origin
    return item


def cmd_write(args):
    bmode_dir = bmode_capture = repo = None
    try:
        bmode_dir, bmode_assets, bmode_capture, capture_py = load_bmode(args.bmode)
        repo = bmode_assets.checkout(args.cwd)
        if repo is None:
            raise DiagnosticError("Run extract-assets inside a Git worktree.")
        tracked_map = dict(list_tracked_files(repo))
    except (DiagnosticError, OSError, ValueError) as err:
        print(_sanitize_text(str(err), repo, bmode_dir, bmode_capture, extra_paths=(args.cwd,)), file=sys.stderr)
        return 2

    try:
        raw = sys.stdin.read() if args.stdin else args.candidates.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError) as err:
        msg = _sanitize_text(f"invalid candidates JSON: {err}", repo, bmode_dir, bmode_capture)
        return _emit_invalid([msg], args.json) if args.json else (print(msg, file=sys.stderr) or 1)

    errors = validate_candidates_envelope(data, repo, bmode_dir, tracked_map, bmode_assets, bmode_capture)
    approve_ids, update_ids, force_ids, override_ids = (
        set(args.approve), set(args.update), set(args.force), set(args.override_bundled)
    )
    if not args.dry_run and not approve_ids:
        errors.append("at least one --approve ID is required unless --dry-run is set")

    candidates = data.get("candidates", []) if isinstance(data, dict) and isinstance(data.get("candidates"), list) else []
    known_ids = {c["id"] for c in candidates if isinstance(c, dict) and isinstance(c.get("id"), str)}
    for flag, id_set in (("--approve", approve_ids), ("--update", update_ids), ("--force", force_ids), ("--override-bundled", override_ids)):
        unknown = sorted(id_set - known_ids)
        if unknown:
            errors.append(f"unknown candidate ID(s) in {flag}: {', '.join(unknown)}")

    selected = []
    if not errors:
        selected = [c for c in candidates if (c["id"] in approve_ids) or (args.dry_run and not approve_ids)]
        targets = {(c["kind"], *bmode_assets.validate_key(c["kind"], c["key"])): c["id"] for c in selected}
        for t_parts, cid in sorted(targets.items()):
            for depth in range(2, len(t_parts)):
                if t_parts[:depth] in targets:
                    errors.append(
                        f"target path collision: '{targets[t_parts[:depth]]}' cannot be both a file and parent directory of '{cid}'"
                    )
    if errors:
        return _emit_invalid(errors, args.json)

    try:
        dedupe_ctx = build_dedupe_context(repo, tracked_map, bmode_dir, bmode_assets)
    except (DiagnosticError, OSError, ValueError) as err:
        print(_sanitize_text(str(err), repo, bmode_dir, bmode_capture), file=sys.stderr)
        return 2

    planned = []
    for cand in selected:
        code, plan, err_msg = _plan_candidate(
            cand, repo, bmode_dir, bmode_assets, bmode_capture, capture_py,
            dedupe_ctx, update_ids, force_ids, override_ids,
        )
        if code in (1, 2):
            sanitized = _sanitize_text(err_msg or "preflight failed", repo, bmode_dir, bmode_capture)
            return _emit_invalid([sanitized], True) if (args.json and code == 1) else (print(sanitized, file=sys.stderr) or code)
        if code == 0 and plan["status"] != "unchanged":
            dedupe_ctx["catalog_entries"].append({
                "origin": "batch", "kind": plan["kind"], "key": plan["key"],
                "trigger": plan["trigger"], "title": plan["title"],
                "content_sha256": plan.get("content_sha256"),
                "tokens": _catalog_tokens(plan["kind"], plan["title"], plan["trigger"]),
            })
        planned.append((code, plan))

    results, had_conflict = [], False
    if args.dry_run:
        for code, plan in planned:
            had_conflict = had_conflict or code == 3
            results.append(_public_plan_item(plan, written=False))
    else:
        for code, plan in planned:
            if code == 3 or not plan["will_write"]:
                had_conflict = had_conflict or code == 3
                results.append(_public_plan_item(plan, written=False))
                continue
            cid, kind, key = plan["id"], plan["kind"], plan["key"]
            validated = None
            if kind in ("playbooks", "workflows"):
                cap_args = ["write", "--stdin", "--json", "--cwd", str(repo)]
                if cid in update_ids:
                    cap_args.append("--update")
                if cid in force_ids:
                    cap_args.append("--force")
                proc = _run_capture_subprocess(capture_py, cap_args, stdin_text=json.dumps(plan["full_payload"]))
                if proc.returncode == 3:
                    had_conflict = True
                    late_plan = dict(plan, status="conflict")
                    try:
                        late_res = json.loads(proc.stdout)
                        late_plan["reason"] = _sanitize_text(late_res.get("reason", "target conflicted during write"), repo, bmode_dir, bmode_capture)
                        late_plan["diff"] = _redact_diff(late_res.get("diff", ""), repo, bmode_dir, bmode_capture)
                    except ValueError:
                        late_plan["reason"] = _sanitize_text(proc.stderr.strip() or proc.stdout.strip() or "target conflicted during write", repo, bmode_dir, bmode_capture)
                    results.append(_public_plan_item(late_plan, written=False))
                    continue
                if proc.returncode != 0:
                    print(_sanitize_text(proc.stderr.strip() or proc.stdout.strip(), repo, bmode_dir, bmode_capture), file=sys.stderr)
                    return proc.returncode
                val_proc = subprocess.run(
                    [sys.executable, "-I", str(capture_py), "validate", f".byte-stack/{kind}/{key}", "--kind", kind, "--json"],
                    cwd=str(repo), capture_output=True, text=True,
                )
                if val_proc.returncode != 0:
                    msg = _sanitize_text(val_proc.stderr.strip() or val_proc.stdout.strip(), repo, bmode_dir, bmode_capture)
                    print(f"post-write validation failed for {cid}: {msg}", file=sys.stderr)
                    return val_proc.returncode
                validated = True
            else:
                try:
                    apply_atomic_write(repo, plan["parts"], kind, plan["rendered"], plan["executable"], plan["expected_bytes"], bmode_assets)
                except TargetChangedError:
                    had_conflict = True
                    late_plan = dict(plan, status="conflict", reason=f"target changed on disk after preflight: {plan['relative_path']}")
                    target = repo / ".byte-stack" / kind / key
                    try:
                        if target.exists() and not target.is_symlink() and stat.S_ISREG(target.lstat().st_mode):
                            cur_norm = target.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
                            late_plan["diff"], _ = _unified_diff_redacted(cur_norm, plan["rendered"], plan["relative_path"], True, repo, bmode_dir, bmode_capture)
                    except OSError:
                        pass
                    results.append(_public_plan_item(late_plan, written=False))
                    continue
                except (DiagnosticError, OSError, ValueError) as err:
                    print(_sanitize_text(str(err), repo, bmode_dir, bmode_capture), file=sys.stderr)
                    return 2

            origin, _ = bmode_assets.resolve(repo, kind, key, bmode_dir)
            if origin != "repo":
                print(f"post-write resolve did not return repo for {cid}", file=sys.stderr)
                return 2
            results.append(_public_plan_item(plan, written=True, validated=validated, resolved_origin=origin))

    exit_code = 3 if had_conflict else 0
    if args.json:
        print(json.dumps({
            "dry_run": args.dry_run, "results": results,
            "schema_version": SCHEMA_VERSION, "status": "conflict" if had_conflict else "ok",
        }, indent=2, sort_keys=True))
    else:
        prefix = "dry-run " if args.dry_run else ""
        for item in results:
            print(f"{prefix}{item['status']}: {item['relative_path']} [verdict={item['verdict']}] ({item['reason']})")
            if item["similar_to"]:
                print("  similar_to: " + ", ".join(f"{s['source']} ({s['score']})" for s in item["similar_to"]))
            if item["diff"]:
                print(item["diff"], end="" if item["diff"].endswith("\n") else "\n")
    return exit_code


def cmd_schema():
    print(SCHEMA_PATH.read_text(encoding="utf-8"), end="")
    return 0


def build_parser():
    top_common = argparse.ArgumentParser(add_help=False)
    top_common.add_argument("--bmode", type=Path, default=None, help="Path to installed bmode skill directory (default: sibling ../bmode)")
    sub_common = argparse.ArgumentParser(add_help=False)
    sub_common.add_argument("--bmode", type=Path, default=argparse.SUPPRESS, help="Path to installed bmode skill directory (default: sibling ../bmode)")

    parser = argparse.ArgumentParser(description=__doc__, parents=[top_common])
    sub = parser.add_subparsers(dest="command", required=True)

    inv_p = sub.add_parser("inventory", parents=[sub_common], help="Scan tracked repository files and .byte-stack/ catalogs (read-only)")
    inv_p.add_argument("--cwd", type=Path, default=Path.cwd(), help="Directory inside target Git worktree")
    inv_p.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES, help="Maximum classified files to read")
    inv_p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="Maximum total bytes to read")
    inv_p.add_argument("--pretty", action="store_true", help="Format inventory JSON with indentation")

    sub.add_parser("schema", parents=[sub_common], help="Print the extract-candidates JSON Schema")

    wr_p = sub.add_parser("write", parents=[sub_common], help="Validate, deduplicate, preview, and write approved .byte-stack/ candidates")
    src = wr_p.add_mutually_exclusive_group(required=True)
    src.add_argument("--candidates", type=Path, help="Path to JSON file matching extract-candidates.schema.json")
    src.add_argument("--stdin", action="store_true", help="Read candidates JSON from stdin")
    wr_p.add_argument("--dry-run", action="store_true", help="Preview verdicts and diffs without writing")
    wr_p.add_argument("--approve", action="append", default=[], metavar="ID", help="Candidate ID (kind/key) approved to write")
    wr_p.add_argument("--update", action="append", default=[], metavar="ID", help="Candidate ID allowed to update an unmodified managed playbook/workflow")
    wr_p.add_argument("--override-bundled", action="append", default=[], metavar="ID", help="Candidate ID allowed to override a bundled byte-stack asset")
    wr_p.add_argument("--force", action="append", default=[], metavar="ID", help="Candidate ID allowed to overwrite differing/manual files or dedupe blocks")
    wr_p.add_argument("--json", action="store_true", help="Print structured JSON result")
    wr_p.add_argument("--cwd", type=Path, default=Path.cwd(), help="Directory inside target Git worktree")
    return parser


def main():
    args = build_parser().parse_args()
    if args.command == "inventory":
        return cmd_inventory(args)
    if args.command == "write":
        return cmd_write(args)
    return cmd_schema()


if __name__ == "__main__":
    sys.exit(main())
