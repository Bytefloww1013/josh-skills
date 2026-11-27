#!/usr/bin/env python3
"""Scan a Git repository and deterministically preview/write .byte-stack/ assets."""
import argparse
import difflib
import errno
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
ALLOWED_CANDIDATE_KEYS = frozenset({"id", "category", "kind", "key", "provenance", "rationale", "payload", "content", "executable"})
ALLOWED_PROVENANCE_KEYS = frozenset({"path", "command", "key", "line"})
ALLOWED_PAYLOAD_SUBKEYS = frozenset({"title", "use_when", "prerequisites", "steps", "verification", "guardrails"})
PUBLIC_PLAN_KEYS = (
    "category", "dedupe_flags", "diff", "id", "key", "kind", "provenance",
    "reason", "relative_path", "similar_to", "status", "verdict", "verdict_reason",
)

SCRIPT_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*(?:/[a-z0-9]+(?:[-_][a-z0-9]+)*)*(?:\.[a-z0-9]+)?$")
_PEM_BEGIN_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_PEM_END_RE = re.compile(r"-----END [A-Z ]*PRIVATE KEY-----")
_BULLET_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")
_WS_RE = re.compile(r"[ \t\r\n]*")

_ABS_PATH_RE = re.compile(r"(?<![\w.])(?<!:/)(?<!<repo>)(?<!<bmode>)(?<!<cwd>)/(?!/)[^\s'\"`<>|;,)\]}]+")
_HOME_SEGMENT_RE = re.compile(r"/(?:home|Users)/[^/\\]")
_WIN_HOME_RE = re.compile(r"[A-Za-z]:\\Users\\[^\s/\\'\"`<>|;,)\]}]+(?:\\[^\s'\"`<>|;,)\]}]*)?")
LINK_FALLBACK_ERRNOS = frozenset(
    code for name in ("EPERM", "EOPNOTSUPP", "ENOTSUP", "EXDEV")
    for code in (getattr(errno, name, None),) if code is not None
)

MAX_CONTENT_BYTES = 65536
MAX_PROVENANCE_READ_BYTES = 1048576
CATALOG_HEAD_BYTES = 4096
DEFAULT_MAX_FILES = 100
DEFAULT_MAX_BYTES = 262144
MAX_SIGNALS_PER_FILE = 30
MAX_SIGNAL_TEXT_LEN = 200

VENDOR_BUILD_DIRS = frozenset({
    "node_modules", "vendor", "third_party", "dist", "build", "target", ".venv", "venv",
    "__pycache__", ".tox", ".nox", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next",
    ".nuxt", ".cache", "coverage", "htmlcov", ".gradle", "Pods", "bower_components", ".terraform", ".eggs",
})
SECRET_NAME_PATTERNS = (
    re.compile(r"^\.env", re.IGNORECASE),
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
    ".editorconfig", ".flake8", ".pylintrc", "pylintrc", ".isort.cfg", ".bandit", ".shellcheckrc",
    ".hadolint.yaml", "biome.json", "biome.jsonc", "pyrightconfig.json", "jsconfig.json",
    "oxlint.json", ".oxlintrc.json", "deno.json", "renovate.json", "ruff.toml", ".ruff.toml",
    "mypy.ini", ".mypy.ini", ".golangci.yml", ".golangci.yaml", "rustfmt.toml", ".rustfmt.toml",
    "clippy.toml", ".clippy.toml", "tsconfig.json",
})
QUALITY_PREFIXES = (
    ".eslintrc", "eslint.config.", ".prettierrc", "prettier.config.",
    "tsconfig.", ".stylelintrc", ".markdownlint", ".yamllint",
)
INI_EXACT_NAMES = frozenset({".editorconfig", ".flake8", ".pylintrc", "pylintrc", ".bandit", ".shellcheckrc"})
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


def _build_sanitizer(repo=None, bmode_dir=None, bmode_capture=None, extra_paths=()):
    """Build (root_pats, secret_pats) for whole-path prefix, secret, and home-path sanitization."""
    root_pats, seen = [], set()
    for path_obj, token in ((repo, "<repo>"), (bmode_dir, "<bmode>"), *((p, "<cwd>") for p in extra_paths)):
        if path_obj is None:
            continue
        for raw in (str(Path(path_obj).resolve()), str(path_obj)):
            clean = raw.rstrip("/\\")
            if clean and clean not in seen:
                seen.add(clean)
                pat = re.compile(r"(?<![\w.-])" + re.escape(clean) + r"(?=$|[^\w.-]|\.(?=$|\s))")
                root_pats.append((len(clean), pat, token))
    root_pats.sort(key=lambda item: item[0], reverse=True)
    return root_pats, (bmode_capture.SECRET_PATTERNS if bmode_capture is not None else ())


def _has_local_path(text):
    """True for a Windows home path, or an absolute path with a home/<name> or Users/<name> segment at any depth."""
    return bool(_WIN_HOME_RE.search(text)) or any(_HOME_SEGMENT_RE.search(m.group()) for m in _ABS_PATH_RE.finditer(text))


def _contains_sensitive(text, sanitizer):
    root_pats, secret_pats = sanitizer
    return any(pat.search(text) for _, pat, _ in root_pats) or any(p.search(text) for p in secret_pats) or _has_local_path(text)


def _sanitize_str(text, sanitizer):
    root_pats, secret_pats = sanitizer
    out = text
    for _, pat, token in root_pats:
        out = pat.sub(token, out)
    for pat in secret_pats:
        out = pat.sub("<redacted-secret>", out)
    out = _WIN_HOME_RE.sub("<local-path>", out)
    return _ABS_PATH_RE.sub(lambda m: "<local-path>" if _HOME_SEGMENT_RE.search(m.group()) else m.group(), out)


def _redact_diff(diff_text, sanitizer):
    """Visibly redact diff lines containing secrets, home paths, or the repo root."""
    if not diff_text:
        return ""
    out, in_pem = [], False
    for line in diff_text.splitlines(keepends=True):
        eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
        body = line[: len(line) - len(eol)] if eol else line
        if body.startswith(("--- ", "+++ ", "@@ ")) or not body or body[0] not in ("-", "+", " "):
            out.append(_sanitize_str(body, sanitizer) + eol)
            continue
        prefix, content = body[0], body[1:]
        if _PEM_BEGIN_RE.search(content):
            in_pem = sensitive = True
        elif in_pem:
            sensitive = True
            in_pem = not bool(_PEM_END_RE.search(content))
        else:
            sensitive = _contains_sensitive(content, sanitizer)
        out.append(f"{prefix}[REDACTED: sensitive content]{eol}" if sensitive else line)
    return "".join(out)


def _sanitize_value(value, sanitizer):
    if isinstance(value, str):
        return _sanitize_str(value, sanitizer)
    if isinstance(value, dict):
        return {
            (_sanitize_str(k, sanitizer) if isinstance(k, str) else k): (
                _redact_diff(v, sanitizer) if k == "diff" and isinstance(v, str) else _sanitize_value(v, sanitizer)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(v, sanitizer) for v in value]
    return value


def _emit(payload, sanitizer, *, as_json=False, pretty=True, stream=None, end="\n"):
    """Single output boundary: sanitize every byte printed to stdout or stderr."""
    clean = _sanitize_value(payload, sanitizer)
    if as_json:
        text = json.dumps(clean, indent=2, sort_keys=True) if pretty else json.dumps(clean, sort_keys=True, separators=(",", ":"))
    else:
        text = str(clean)
    print(text, file=sys.stdout if stream is None else stream, end=end)


def _emit_invalid(errors, as_json, sanitizer):
    if as_json:
        _emit({"errors": errors, "status": "invalid"}, sanitizer, as_json=True)
    else:
        _emit("\n".join(f"candidate error: {err}" for err in errors), sanitizer, stream=sys.stderr)
    return 1


def _read_unbuffered(path, limit):
    """Read at most `limit` bytes unbuffered so kernel reads never exceed the budget."""
    chunks, remaining = [], limit
    with path.open("rb", buffering=0) as handle:
        while remaining > 0:
            chunk = handle.read(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    return b"".join(chunks)


def _drop_unfinished_line(raw, truncated):
    if not truncated or raw.endswith(b"\n"):
        return raw
    last_nl = raw.rfind(b"\n")
    return raw[: last_nl + 1] if last_nl != -1 else b""


def _check_utf8(label, text, errors):
    try:
        text.encode("utf-8")
        return True
    except UnicodeEncodeError:
        errors.append(f"{label} must contain valid UTF-8 characters (no lone surrogates)")
        return False


def _check_safety_patterns(bmode_capture, label, text, errors, tracked_path=False):
    """Apply capture's guards plus the absolute home-path rule; a tracked path is relative, so only the latter."""
    capture_local = () if (bmode_capture is None or tracked_path) else bmode_capture.LOCAL_PATH_PATTERNS
    without_urls = text if bmode_capture is None else bmode_capture.WEB_URL_PATTERN.sub(" ", text)
    if _has_local_path(text) or any(p.search(without_urls) for p in capture_local):
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
    result = subprocess.run(["git", "-C", str(repo), "ls-files", "-s", "-z"], capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"})
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


def _init_worktree(args):
    """Load bmode, resolve the Git worktree, list tracked files, and build the sanitizer."""
    bmode_dir = bmode_capture = repo = None
    try:
        bmode_dir, bmode_assets, bmode_capture, capture_py = load_bmode(args.bmode)
        repo = bmode_assets.checkout(args.cwd)
        if repo is None:
            raise DiagnosticError("Run extract-assets inside a Git worktree.")
        tracked = list_tracked_files(repo)
    except (DiagnosticError, OSError, ValueError) as err:
        _emit(str(err), _build_sanitizer(repo, bmode_dir, bmode_capture, extra_paths=(args.cwd, args.bmode)), stream=sys.stderr)
        return None
    return repo, bmode_dir, bmode_assets, bmode_capture, capture_py, tracked, _build_sanitizer(repo, bmode_dir, bmode_capture)


def exclusion_reason(rel_path, mode, bmode_capture=None):
    """Return exclusion reason string for a path (checking every segment), or None."""
    if mode in ("120000", "160000"):
        return "symlink" if mode == "120000" else "submodule"
    parts = rel_path.split("/")
    if any(part in VENDOR_BUILD_DIRS for part in parts[:-1]):
        return "vendored_or_build"
    if any(pat.search(part) for part in parts for pat in SECRET_NAME_PATTERNS) or (
        bmode_capture is not None and any(pat.search(rel_path) for pat in bmode_capture.SECRET_PATTERNS)
    ):
        return "secret_file"
    if any(pat.search(part) for part in parts for pat in MACHINE_LOCAL_PATTERNS) or (
        bmode_capture is not None and _has_local_path(rel_path)
    ):
        return "machine_local"
    return None


def classify_path(rel_path, mode):
    """Classify a non-excluded tracked path into an inventory bucket, or None."""
    parts = rel_path.split("/")
    if parts[0] == ".byte-stack":
        return None
    lower_path, lower_name = rel_path.lower(), parts[-1].lower()
    suffix = Path(lower_name).suffix
    if (len(parts) >= 3 and parts[0] == ".github" and parts[1] == "workflows" and suffix in (".yml", ".yaml")) or lower_path in CI_PATHS or (len(parts) >= 2 and parts[0] == ".buildkite" and suffix in (".yml", ".yaml")):
        return "ci"
    if lower_path in HOOK_PATHS or (parts[0] == ".husky" and len(parts) == 2 and not lower_name.startswith("_")) or (parts[0] in (".githooks", "githooks") and len(parts) >= 2) or lower_name.startswith((".lintstagedrc", "lint-staged.config.")):
        return "git_hooks"
    if lower_name in STEERING_NAMES or lower_path in (".github/copilot-instructions.md", ".cursorrules") or lower_path.startswith(".cursor/rules/"):
        return "steering"
    if suffix in (".md", ".mdx") and lower_path.startswith(("docs/adr/", "docs/adrs/", "docs/decisions/", "adr/", "adrs/")):
        return "adrs"
    if (lower_path.startswith(("docs/directives/", "docs/standards/", "docs/guidelines/", "docs/policies/")) and suffix in (".md", ".mdx", ".txt")) or lower_name in DIRECTIVE_NAMES or lower_path in DIRECTIVE_PATHS:
        return "directives"
    if lower_name in QUALITY_EXACT_NAMES or any(lower_name.startswith(p) for p in QUALITY_PREFIXES) or lower_path in (".github/dependabot.yml", ".github/dependabot.yaml"):
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
            chunk, closed = (s.split(end_delim, 1)[0], True) if end_delim in s else (s, False)
            body = chunk.lstrip("* ").strip() if (closed or end_delim == "*/") else chunk
            if closed:
                end_delim = None
            if body:
                return idx, body
            continue
        block = next(((st, en) for st, en in (('"""', '"""'), ("'''", "'''"), ("/*", "*/")) if s.startswith(st)), None)
        if block:
            rest = s[len(block[0]):]
            chunk, closed = (rest.split(block[1], 1)[0], True) if block[1] in rest else (rest, False)
            body = chunk.lstrip("* ").strip() if (closed or block[1] == "*/") else chunk.strip()
            if body:
                return idx, body
            if not closed:
                end_delim = block[1]
            continue
        if s.startswith(("#", "//")):
            body = s.lstrip("#/").strip()
            if body and not (set(body) <= {"-", "=", "*"}):
                return idx, body
            continue
        break
    return None


def _has_structured_extractor(rel_path):
    lower_name = Path(rel_path).name.lower()
    return Path(lower_name).suffix in (".json", ".jsonc", ".yml", ".yaml", ".mk", ".toml", ".ini", ".cfg") or lower_name in ("makefile", "gnumakefile", "justfile") or lower_name in INI_EXACT_NAMES


def _walk_json_keys(text):
    """Return [(dotted_key, 1-based line_no, value, parent_key), ...] for object properties in valid JSON, or None."""
    dec, n, out = json.JSONDecoder(), len(text), []

    def walk_obj(i, prefix, depth):
        i = _WS_RE.match(text, i + 1).end()
        if i < n and text[i] == "}":
            return i + 1
        while i < n:
            key, end_k = dec.raw_decode(text, i)
            if not isinstance(key, str):
                raise ValueError("expected string key")
            key_line, i = text.count("\n", 0, i) + 1, _WS_RE.match(text, end_k).end()
            if i >= n or text[i] != ":":
                raise ValueError("expected ':'")
            i = _WS_RE.match(text, i + 1).end()
            fk = f"{prefix}.{key}" if prefix else key
            val, end_v = dec.raw_decode(text, i)
            out.append((fk, key_line, val, prefix))
            if isinstance(val, dict) and depth < 3:
                walk_obj(i, fk, depth + 1)
            i = _WS_RE.match(text, end_v).end()
            if i < n and text[i] == ",":
                i = _WS_RE.match(text, i + 1).end()
                continue
            if i < n and text[i] == "}":
                return i + 1
            raise ValueError("expected ',' or '}'")
        raise ValueError("unterminated object")

    start = _WS_RE.match(text, 0).end()
    if start < n and text[start] == "{":
        try:
            walk_obj(start, "", 0)
        except ValueError:
            return None
    return out


def _logical_lines(file_lines):
    """Return [(1-based start_line, joined_text), ...] merging trailing backslash continuations."""
    out, idx = [], 0
    while idx < len(file_lines):
        start_ln, parts = idx + 1, []
        while idx < len(file_lines):
            line = file_lines[idx]
            idx += 1
            if line.rstrip().endswith("\\") and idx < len(file_lines):
                parts.append(line.rstrip()[:-1])
                continue
            parts.append(line)
            break
        out.append((start_ln, " ".join(parts)))
    return out


def extract_signals(rel_path, text, sanitizer=None, bucket=None, for_provenance=False):
    """Extract signals (commands, keys, headings, or one script summary) with exact 1-based lines."""
    signals, truncated_signals, dropped_sensitive = [], False, 0
    lines = text.splitlines()
    lower_name = Path(rel_path).name.lower()
    suffix = Path(lower_name).suffix

    def add_signal(kind, line_no, raw_text, key_name=None):
        nonlocal truncated_signals, dropped_sensitive
        if not for_provenance and sanitizer is not None and (
            _contains_sensitive(raw_text, sanitizer) or (key_name is not None and _contains_sensitive(key_name, sanitizer))
        ):
            dropped_sensitive += 1
            return
        collapsed = " ".join(raw_text.strip().split())
        if not collapsed:
            return
        if not for_provenance and len(collapsed) > MAX_SIGNAL_TEXT_LEN:
            collapsed, truncated_signals = collapsed[: MAX_SIGNAL_TEXT_LEN - 3] + "...", True
        if not for_provenance and len(signals) >= MAX_SIGNALS_PER_FILE:
            truncated_signals = True
            return
        sig = {"kind": kind, "line": line_no, "text": collapsed}
        if key_name is not None:
            sig["key"] = key_name
        signals.append(sig)

    if not for_provenance and bucket == "scripts":
        summary = _extract_script_summary(lines)
        if summary is not None:
            add_signal("summary", summary[0], summary[1])
        return signals, truncated_signals, dropped_sensitive

    if suffix in (".md", ".mdx"):
        in_fence, fence_shell, joined = False, False, dict(_logical_lines(lines))
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("```"):
                lang = stripped[3:].strip().lower().split()[0] if (not in_fence and stripped[3:].strip()) else ""
                in_fence, fence_shell = (not in_fence), (not in_fence and lang in ("sh", "bash", "shell", "zsh", "console", ""))
            elif not in_fence and re.match(r"^#{1,4}\s+\S", stripped):
                add_signal("heading", idx, stripped)
            elif in_fence and fence_shell and stripped and not stripped.startswith("#") and idx in joined:
                cmd = joined[idx].strip()
                add_signal("command", idx, cmd[2:].strip() if cmd.startswith("$ ") else cmd)
    elif suffix in (".json", ".jsonc"):
        entries = _walk_json_keys(text)
        if entries is not None:
            for fk, ln, val, parent in entries:
                if lower_name == "package.json":
                    if parent == "scripts" and isinstance(val, str):
                        add_signal("command", ln, val, key_name=fk)
                    elif not parent and fk != "scripts":
                        add_signal("key", ln, fk)
                else:
                    add_signal("key", ln, fk)
        else:
            for idx, line in enumerate(lines, 1):
                m = re.match(r'^\s{1,2}"([^"]+)"\s*:', line)
                if m and not (lower_name == "package.json" and m.group(1) == "scripts"):
                    add_signal("key", idx, m.group(1))
    elif suffix in (".yml", ".yaml"):
        in_run_block, run_indent, cont_parts, cont_line = False, 0, [], None

        def flush_cont():
            nonlocal cont_parts, cont_line
            if cont_parts:
                add_signal("command", cont_line, " ".join(p for p in cont_parts if p))
                cont_parts, cont_line = [], None

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            if in_run_block:
                if indent > run_indent:
                    cont_line = idx if cont_line is None else cont_line
                    cont_parts.append(stripped[:-1].rstrip() if stripped.endswith("\\") else stripped)
                    if not stripped.endswith("\\"):
                        flush_cont()
                    continue
                flush_cont()
                in_run_block = False
            m_run = re.match(r"^(\s*)(?:-\s*)?run:\s*(.*)$", line)
            if m_run:
                val = m_run.group(2).strip()
                if re.fullmatch(r"[|>][+-]?\d*(?:\s+#.*)?", val):
                    in_run_block, run_indent = True, indent
                elif val:
                    add_signal("command", idx, val[1:-1] if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'") else val)
                continue
            m_uses = re.match(r"^\s*(?:-\s*)?((?:uses|repo|id):\s*.+)$", line)
            if m_uses:
                add_signal("key", idx, m_uses.group(1).strip())
            elif indent == 0:
                m_top = re.match(r"^([A-Za-z0-9_.-]+):", line)
                if m_top:
                    add_signal("key", idx, m_top.group(1))
        flush_cont()
    elif lower_name in ("makefile", "gnumakefile", "justfile") or suffix == ".mk":
        for start_ln, line in _logical_lines(lines):
            if line.startswith("\t") or (lower_name == "justfile" and line.startswith(" ")):
                cmd = " ".join(line.strip().split())
                if cmd and not cmd.startswith("#"):
                    add_signal("command", start_ln, cmd.lstrip("@-+").strip())
                continue
            m_target = re.match(r"^([A-Za-z0-9_./-]+)\s*:(?!=)", line)
            if m_target and not m_target.group(1).startswith("."):
                add_signal("key", start_ln, m_target.group(1))
    elif suffix in (".toml", ".ini", ".cfg") or lower_name in INI_EXACT_NAMES:
        current_sec, in_scripts = "", False
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";")):
                continue
            m_sec = re.match(r"^\[{1,2}([^\]]+)\]{1,2}\s*(?:[#;].*)?$", stripped)
            if m_sec:
                current_sec = m_sec.group(1).strip()
                add_signal("key", idx, current_sec)
                in_scripts = current_sec.endswith("scripts")
            elif "=" in stripped:
                k, v = (part.strip() for part in stripped.split("=", 1))
                fk = f"{current_sec}.{k}" if current_sec else k
                if in_scripts:
                    add_signal("command", idx, v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'") else v, key_name=fk)
                elif not line.startswith((" ", "\t")) and " " not in k:
                    add_signal("key", idx, fk)
    else:
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if idx == 1 and stripped.startswith("#!"):
                add_signal("heading", idx, stripped)
            elif re.match(r"^(?:def|async def|function|export function)\s+[A-Za-z0-9_-]+", stripped):
                add_signal("heading", idx, stripped.split("{")[0].rstrip(":"))
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
    return _tokenize(f"{title} {trigger}") if kind in ("playbooks", "workflows") else (_tokenize(title) if kind == "references" else frozenset())


def _inspect_markdown_head(text, path_label, bmode_assets):
    """Parse frontmatter, trigger, and H1 title from a bounded Markdown head."""
    if not text.strip():
        raise ValueError(f"empty asset: {path_label}")
    meta, body = bmode_assets.parse_frontmatter(text, path_label)
    if not body.strip():
        raise ValueError(f"empty asset: {path_label}")
    fm_trigger = meta.get("use-when", "").strip()
    body_trigger = next((line.removeprefix("Use when: ").strip() for line in body.splitlines() if line.startswith("Use when: ")), "")
    if fm_trigger and body_trigger and fm_trigger != body_trigger:
        raise ValueError(f"conflicting trigger descriptions: {path_label}")
    return fm_trigger or body_trigger, _extract_h1(body)


def read_bundled_catalog(bmode_assets, bmode_dir):
    """Enumerate bundled bmode assets across all four kinds once."""
    by_kind = {}
    for kind in bmode_assets.KINDS:
        entries, base = {}, bmode_dir / kind
        if base.is_dir():
            for path in sorted(base.rglob("*")):
                rel = path.relative_to(base)
                if any(p.startswith(".") or p == "__pycache__" for p in rel.parts) or path.is_dir() or (kind in ("playbooks", "workflows") and path.suffix != ".md"):
                    continue
                key, trigger = rel.as_posix(), bmode_assets.inspect_file(path, kind)
                raw = path.read_bytes() if path.stat().st_size <= MAX_CONTENT_BYTES else None
                sha = hashlib.sha256(raw).hexdigest() if raw is not None else None
                title = _extract_h1(raw.decode("utf-8", errors="replace") if raw is not None else path.read_text(encoding="utf-8", errors="replace")) if path.suffix == ".md" else ""
                entries[key] = {"origin": "bundled", "kind": kind, "key": key, "trigger": trigger, "title": title, "content_sha256": sha, "tokens": _catalog_tokens(kind, title, trigger)}
        by_kind[kind] = entries
    return by_kind


def _walk_repo_kind_dir(r_base, kind, bmode_capture=None, on_excl=None, on_error=None):
    """Yield (rel_posix, path, lstat) under .byte-stack/<kind>/ safely without following symlinks."""
    def fail(err):
        if on_error:
            on_error(err)
            return
        raise err

    def recurse(cur_dir):
        try:
            children = sorted(cur_dir.iterdir(), key=lambda p: p.name)
        except OSError as err:
            fail(err)
            return
        for child in children:
            rel_parts = child.relative_to(r_base).parts
            rel_posix = "/".join(rel_parts)
            if child.is_symlink():
                fail(ValueError(f"symlink in asset path: {child}"))
                continue
            try:
                st = child.lstat()
            except OSError as err:
                fail(err)
                continue
            is_dir = stat.S_ISDIR(st.st_mode)
            excl = exclusion_reason(f"{rel_posix}/_" if is_dir else rel_posix, "100644", bmode_capture)
            if excl is not None:
                if on_excl:
                    on_excl(f".byte-stack/{kind}/{rel_posix}", excl)
                continue
            if any(p.startswith(".") or p == "__pycache__" for p in rel_parts):
                continue
            if is_dir:
                yield from recurse(child)
            elif kind in ("playbooks", "workflows") and child.suffix != ".md":
                continue
            elif not stat.S_ISREG(st.st_mode):
                fail(ValueError(f"expected regular file: {child}"))
            else:
                yield rel_posix, child, st

    yield from recurse(r_base)


def _has_budget(budget):
    if budget["files_read"] >= budget["max_files"]:
        budget["truncated"]["files"] = True
        budget["bump"]("max_files_limit")
        return False
    if budget["bytes_remaining"] <= 0:
        budget["truncated"]["bytes"] = True
        budget["bump"]("max_bytes_limit")
        return False
    return True


def collect_byte_stack_inventory(repo, bmode_dir, bmode_assets, bmode_capture, budget, excluded_paths):
    """Inspect bundled and repo .byte-stack catalogs with exclusions, shared budget, and strict checks."""
    bundled_all, catalog_out, diagnostics = read_bundled_catalog(bmode_assets, bmode_dir), {}, []

    def add_diag(kind, message):
        diagnostics.append({"kind": kind, "message": str(message), "scope": "byte_stack"})

    def note_excl(repo_rel, reason):
        if repo_rel not in excluded_paths:
            excluded_paths.add(repo_rel)
            budget["bump"](reason)

    for kind in bmode_assets.KINDS:
        bundled, repo_items, r_base = bundled_all[kind], {}, None
        try:
            cand_base = bmode_assets.checked(repo, [".byte-stack", kind])
            if cand_base.exists() and not cand_base.is_dir():
                raise ValueError(f"expected directory: {cand_base}")
            r_base = cand_base if cand_base.exists() else None
        except (OSError, ValueError) as err:
            add_diag(kind, err)

        if r_base is not None:
            for key, path, st in _walk_repo_kind_dir(
                r_base, kind, bmode_capture=bmode_capture, on_excl=note_excl, on_error=lambda err, k=kind: add_diag(k, err)
            ):
                try:
                    bmode_assets.validate_key(kind, key)
                except ValueError as err:
                    add_diag(kind, err)
                    continue
                if not _has_budget(budget):
                    continue
                head_truncated = False
                try:
                    if kind != "scripts" and path.suffix == ".md":
                        read_cap = min(CATALOG_HEAD_BYTES, budget["bytes_remaining"])
                        raw = _read_unbuffered(path, read_cap)
                        budget["files_read"] += 1
                        budget["bytes_remaining"] -= len(raw)
                        head_truncated = len(raw) < st.st_size
                        if head_truncated and read_cap < CATALOG_HEAD_BYTES:
                            budget["truncated"]["bytes"] = True
                        if b"\x00" in raw:
                            budget["bump"]("binary")
                            continue
                        parse_raw = _drop_unfinished_line(raw, head_truncated)
                        if head_truncated and not parse_raw:
                            budget["truncated"]["bytes"] = True
                            add_diag(kind, f"trigger not established within first {len(raw)} bytes: {path}")
                            continue
                        trigger, _ = _inspect_markdown_head(parse_raw.decode("utf-8"), path, bmode_assets)
                        if kind == "playbooks" and not trigger:
                            trigger = bundled[key]["trigger"] if key in bundled else ""
                            if not trigger:
                                if head_truncated:
                                    budget["truncated"]["bytes"] = True
                                add_diag(kind, f"missing 'Use when: ' description{' within first ' + str(len(raw)) + ' bytes' if head_truncated else ''}: {path}")
                                continue
                    else:
                        with path.open("rb", buffering=0):
                            pass
                        budget["files_read"] += 1
                        trigger = ""
                except (OSError, ValueError) as err:
                    if head_truncated:
                        budget["truncated"]["bytes"] = True
                    msg = str(err)
                    add_diag(kind, msg if str(path) in msg else f"{msg}: {path}")
                    continue
                repo_items[key] = {"key": key, "origin": "repo", "overrides_bundled": key in bundled, "repo_path": f".byte-stack/{kind}/{key}", "trigger": trigger, **({"truncated": True} if head_truncated else {})}

        catalog_out[kind] = [
            repo_items[k] if k in repo_items else {"key": bundled[k]["key"], "origin": "bundled", "overrides_bundled": False, "trigger": bundled[k]["trigger"]}
            for k in sorted(set(bundled) | set(repo_items))
        ]

    diagnostics.sort(key=lambda d: (d["scope"], d["kind"], d["message"]))
    return catalog_out, diagnostics


def cmd_inventory(args):
    if args.max_files < 1 or args.max_bytes < 1:
        _emit("--max-files and --max-bytes must be positive integers", _build_sanitizer(), stream=sys.stderr)
        return 1
    ctx = _init_worktree(args)
    if ctx is None:
        return 2
    repo, bmode_dir, bmode_assets, bmode_capture, _, tracked, sanitizer = ctx

    categories = {k: [] for k in ("adrs", "ci", "directives", "git_hooks", "quality", "scripts", "steering", "task_runners")}
    exclusions, excluded_paths, unclassified_count = {}, set(), 0
    truncated = {"bytes": False, "files": False, "signals": False}

    def bump_exclusion(reason, count=1):
        if count > 0:
            exclusions[reason] = exclusions.get(reason, 0) + count

    budget = {"files_read": 0, "bytes_remaining": args.max_bytes, "max_files": args.max_files, "truncated": truncated, "bump": bump_exclusion}

    for rel_path, mode in tracked:
        reason = exclusion_reason(rel_path, mode, bmode_capture)
        if reason is not None:
            excluded_paths.add(rel_path)
            bump_exclusion(reason)
            continue
        bucket = classify_path(rel_path, mode)
        if bucket is None:
            if not rel_path.startswith(".byte-stack/"):
                unclassified_count += 1
            continue
        if not _has_budget(budget):
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
            raw = _read_unbuffered(target, budget["bytes_remaining"])
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

        text = _drop_unfinished_line(raw, file_truncated).decode("utf-8", errors="replace")
        signals, sig_truncated, dropped = extract_signals(rel_path, text, sanitizer=sanitizer, bucket=bucket)
        if sig_truncated:
            file_truncated = truncated["signals"] = True
        bump_exclusion("sensitive_signals_dropped", dropped)
        categories[bucket].append({
            "bytes": st.st_size, "bytes_read": bytes_read, "lines": len(text.splitlines()),
            "path": rel_path, "signals": signals, "truncated": file_truncated, **({"signals_withheld": dropped} if dropped else {}),
        })

    for bucket in categories:
        categories[bucket].sort(key=lambda item: item["path"])
    byte_stack_catalog, diagnostics = collect_byte_stack_inventory(repo, bmode_dir, bmode_assets, bmode_capture, budget, excluded_paths)
    output = {
        "byte_stack": byte_stack_catalog, "categories": categories, "diagnostics": diagnostics,
        "exclusions": dict(sorted(exclusions.items())),
        "limits": {"max_bytes": args.max_bytes, "max_files": args.max_files, "max_signals_per_file": MAX_SIGNALS_PER_FILE},
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "bytes_read": args.max_bytes - budget["bytes_remaining"], "files_read": budget["files_read"],
            "tracked_files": len(tracked), "unclassified_tracked_files": unclassified_count,
        },
        "truncated": truncated,
    }
    _emit(output, sanitizer, as_json=True, pretty=args.pretty)
    return 0


def _verbatim_command_pattern(cmd):
    tokens = cmd.split()
    return re.compile(r"(?:^|[\s'\"`])" + r"\s+".join(re.escape(tok) for tok in tokens) + r"(?=$|[\s'\"`])") if tokens else None


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
        items = [p.get("title", ""), p.get("use_when", "")]
        for field in ("prerequisites", "steps", "verification", "guardrails"):
            items.extend(p.get(field, []))
        return [item.strip() for item in items if item and item.strip()]
    return [line.strip() for line in _normalize_lf(candidate["content"]).splitlines() if line.strip() and line.strip() != "---"]


def _check_payload_strings(prefix, payload, bmode_capture, errors):
    """Validate UTF-8 and bare/non-ASCII machine-local paths across payload string fields."""
    utf8_ok = True
    checks = [(f, payload[f]) for f in ("title", "use_when") if isinstance(payload.get(f), str)]
    for f in ("prerequisites", "steps", "verification", "guardrails"):
        if isinstance(payload.get(f), list):
            checks.extend((f"{f}[{i}]", item) for i, item in enumerate(payload[f]) if isinstance(item, str))
    for label, val in checks:
        if not _check_utf8(f"{prefix}.payload.{label}", val, errors):
            utf8_ok = False
        elif _has_local_path(val) and not any(p.search(val) for p in bmode_capture.LOCAL_PATH_PATTERNS):
            errors.append(f"{prefix}.payload: {label} must not contain a machine-local home path")
    return utf8_ok


def validate_candidates_envelope(data, repo, tracked_map, bmode_assets, bmode_capture):
    """Validate candidate envelope, per-kind rules, UTF-8, safety patterns, and provenance."""
    if not isinstance(data, dict):
        return ["candidates input must be a JSON object"]
    errors = []

    def check_unknown(obj, allowed, label):
        extra = sorted(set(obj) - allowed)
        if extra:
            errors.append(f"{label} {', '.join(extra)}")

    check_unknown(data, ALLOWED_ENVELOPE_KEYS, "unknown envelope field(s):")
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
            text = _read_unbuffered(target, MAX_PROVENANCE_READ_BYTES).decode("utf-8", errors="replace")
            file_lines = text.splitlines()
            if _has_structured_extractor(rel_path):
                sigs, _, _ = extract_signals(rel_path, text, for_provenance=True)
                def forms(value):  # the full text, plus the shortened form the inventory prints for a long one
                    return (value,) if len(value) <= MAX_SIGNAL_TEXT_LEN else (value, value[: MAX_SIGNAL_TEXT_LEN - 3] + "...")
                cmds = [(s["line"], f) for s in sigs if s["kind"] == "command" for f in forms(s["text"])]
                keys = [(s["line"], f) for s in sigs for f in (forms(s["text"]) if s["kind"] == "key" else ()) + ((s["key"],) if "key" in s else ())]
                file_cache[rel_path] = (len(file_lines), True, cmds, keys)
            else:
                file_cache[rel_path] = (len(file_lines), False, _logical_lines(file_lines), None)
        return file_cache[rel_path]

    for idx, cand in enumerate(candidates):
        prefix = f"candidates[{idx}]"
        if not isinstance(cand, dict):
            errors.append(f"{prefix} must be an object")
            continue
        check_unknown(cand, ALLOWED_CANDIDATE_KEYS, f"{prefix} has unknown field(s):")
        for req in ("id", "category", "kind", "key", "provenance"):
            if req not in cand:
                errors.append(f"{prefix} missing required field: {req}")

        for field, allowed in (("category", ALLOWED_CATEGORIES), ("kind", ALLOWED_KINDS)):
            val = cand.get(field)
            if field in cand and (not isinstance(val, str) or (_check_utf8(f"{prefix}.{field}", val, errors) and val not in allowed)):
                errors.append(f"{prefix}.{field} must be one of: {', '.join(allowed)}")
        kind = cand.get("kind")
        valid_kind = isinstance(kind, str) and kind in ALLOWED_KINDS

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
                    if kind in ("playbooks", "workflows", "references") and (not (4 <= len(key) <= 120) or not bmode_capture.KEY_PATTERN.fullmatch(key)):
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
                    check_unknown(prov, ALLOWED_PROVENANCE_KEYS, f"{pl} has unknown field(s):")
                    ppath = prov.get("path")
                    if not isinstance(ppath, str) or not ppath.strip():
                        errors.append(f"{pl}.path must be a non-empty string")
                        continue
                    if not _check_utf8(f"{pl}.path", ppath, errors):
                        continue
                    _check_safety_patterns(bmode_capture, f"{pl}.path", ppath, errors, tracked_path=True)
                    if ppath.startswith("/") or "\\" in ppath or ".." in ppath.split("/"):
                        errors.append(f"{pl}.path must be a repo-relative POSIX path")
                        continue
                    if ppath not in tracked_map:
                        errors.append(f"{pl}.path is not a tracked repository file: {ppath}")
                        continue
                    excl = exclusion_reason(ppath, tracked_map[ppath], bmode_capture)
                    if excl is not None:
                        errors.append(f"{pl}.path is excluded ({excl}): {ppath}")
                        continue
                    try:
                        line_count, structured, prov_data, ext_keys = read_provenance_file(ppath)
                    except (OSError, ValueError) as err:
                        errors.append(f"{pl}.path unreadable or unsafe: {err}")
                        continue

                    valid_line = None
                    if "line" in prov:
                        line_no = prov["line"]
                        if isinstance(line_no, bool) or not isinstance(line_no, int) or line_no < 1:
                            errors.append(f"{pl}.line must be a positive integer")
                        elif line_no > line_count:
                            errors.append(f"{pl}.line {line_no} exceeds {ppath} length ({line_count} lines)")
                        else:
                            valid_line = line_no

                    where = f" at line {valid_line}" if valid_line is not None else ""
                    if "command" in prov:
                        cmd = prov["command"]
                        if not isinstance(cmd, str) or not cmd.strip() or len(cmd) > 400:
                            errors.append(f"{pl}.command must be a non-empty string (<= 400 chars)")
                        elif _check_utf8(f"{pl}.command", cmd, errors):
                            _check_safety_patterns(bmode_capture, f"{pl}.command", cmd, errors)
                            if valid_line is not None or "line" not in prov:
                                if structured:
                                    norm_cmd = " ".join(cmd.split())
                                    matched = any(t == norm_cmd and (valid_line is None or ln == valid_line) for ln, t in prov_data)
                                else:
                                    pat = _verbatim_command_pattern(cmd)
                                    matched = bool(pat) and any((valid_line is None or ln == valid_line) and pat.search(lt) for ln, lt in prov_data)
                                if not matched:
                                    errors.append(f"{pl}.command not found{where} in {ppath}; cite the command text as printed by inventory, or cite path plus line")

                    if "key" in prov:
                        pkey = prov["key"]
                        if not isinstance(pkey, str) or not pkey.strip() or len(pkey) > 200:
                            errors.append(f"{pl}.key must be a non-empty string (<= 200 chars)")
                        elif _check_utf8(f"{pl}.key", pkey, errors):
                            _check_safety_patterns(bmode_capture, f"{pl}.key", pkey, errors)
                            if not structured:
                                errors.append(f"{pl}.key is not supported for {ppath}; cite path and line instead")
                            elif valid_line is not None or "line" not in prov:
                                norm_key = " ".join(pkey.split())
                                if not any(k == norm_key and (valid_line is None or ln == valid_line) for ln, k in ext_keys):
                                    errors.append(f"{pl}.key not found{where} in {ppath}; cite the key text as printed by inventory, or cite path plus line")

        if valid_kind and kind in ("playbooks", "workflows"):
            if "content" in cand:
                errors.append(f"{prefix}.content is not allowed for {kind}; use payload")
            if "payload" not in cand:
                errors.append(f"{prefix}.payload is required for {kind}")
            elif not isinstance(cand["payload"], dict):
                errors.append(f"{prefix}.payload must be an object")
            else:
                payload = cand["payload"]
                if set(payload) - ALLOWED_PAYLOAD_SUBKEYS:
                    check_unknown(payload, ALLOWED_PAYLOAD_SUBKEYS, f"{prefix}.payload has unknown field(s):")
                elif _check_payload_strings(prefix, payload, bmode_capture, errors):
                    full_payload = {"schema_version": SCHEMA_VERSION, "kind": kind, "key": key if valid_str_key else "placeholder.md", **payload}
                    errors.extend(f"{prefix}.payload: {perr}" for perr in bmode_capture.validate_payload(full_payload) if valid_str_key or not perr.startswith("key"))
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
                head = _read_unbuffered(path, CATALOG_HEAD_BYTES)
            if kind != "scripts" and path.suffix == ".md" and b"\x00" not in head:
                head_txt = head.decode("utf-8", errors="replace")
                try:
                    trigger, title = _inspect_markdown_head(head_txt, path, bmode_assets)
                except ValueError:
                    title = _extract_h1(head_txt)
            catalog_entries.append({"origin": "repo", "kind": kind, "key": key, "trigger": trigger, "title": title, "content_sha256": sha, "tokens": _catalog_tokens(kind, title, trigger)})

    steering_lines, steering_sources = set(), []
    for rel_path, mode in sorted(tracked_map.items()):
        if exclusion_reason(rel_path, mode) is not None or classify_path(rel_path, mode) != "steering":
            continue
        try:
            target = bmode_assets.checked(repo, rel_path.split("/"))
            _check_regular(target)
            if not target.exists():
                continue
            text = _read_unbuffered(target, MAX_PROVENANCE_READ_BYTES).decode("utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        unbulleted = set()
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if stripped:
                steering_lines.add(stripped)
                ub = _BULLET_RE.sub("", stripped).strip()
                if ub:
                    unbulleted.add(ub)
        steering_sources.append((rel_path, _tokenize(text), unbulleted))

    return {"bundled": bundled_by_kind, "catalog_entries": catalog_entries, "steering_lines": steering_lines, "steering_sources": steering_sources}


def _token_similarity(tokens_a, tokens_b):
    if not tokens_a or not tokens_b:
        return 0, 0.0, 0.0
    shared = len(tokens_a & tokens_b)
    return shared, shared / len(tokens_a | tokens_b), shared / min(len(tokens_a), len(tokens_b))


def evaluate_dedupe(candidate, exists, is_identical, rendered_bytes, rendered_text, ctx, ref_trigger=""):
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

    cand_trigger = _normalize_title_or_trigger(candidate["payload"].get("use_when", "") if kind in ("playbooks", "workflows") else ref_trigger)
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

    verdict = next((v for v in ("exists-identical", "exists-differs", "overrides-bundled", "restates-steering", "duplicates-catalog") if v in flags), "new")
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
        cand_ub = [ub for l in cand_lines for ub in (_BULLET_RE.sub("", l).strip(),) if ub]
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
    """Write a references/ or scripts/ file atomically with pre-replace inspection and no-clobber create."""
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
        mode = ((existing_mode | 0o111) & ~umask if (kind == "scripts" and executable is True) else existing_mode) if existing_mode is not None else ((0o777 if (kind == "scripts" and executable is True) else 0o666) & ~umask)
        os.chmod(tmp_path, mode)
        bmode_assets.inspect_file(tmp_path, kind)
        if expected_bytes is None:
            try:
                try:
                    os.link(tmp_path, target)
                except OSError as err:
                    if isinstance(err, FileExistsError) or err.errno not in LINK_FALLBACK_ERRNOS:
                        raise
                    out_fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), mode)
                    created = True
                    try:
                        with os.fdopen(out_fd, "wb") as out_handle:
                            out_handle.write(content.encode("utf-8"))
                        os.chmod(target, mode)
                        created = False
                    finally:
                        if created:
                            target.unlink(missing_ok=True)
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
    return subprocess.run([sys.executable, "-I", str(capture_py), *subcmd_args], input=stdin_text, capture_output=True, text=True)


def _capture_write_args(repo, *, dry_run, allow_update, allow_force):
    return ["write", "--stdin", "--json", "--cwd", str(repo), *(["--dry-run"] if dry_run else []), *(["--update"] if allow_update else []), *(["--force"] if allow_force else [])]


def _blocking_dedupe_reason(cid, flags, allow_override, allow_duplicate):
    parts = []
    if "restates-steering" in flags and not allow_duplicate:
        parts.append(f"candidate restates steering files; pass --allow-duplicate {cid} to write anyway")
    if "duplicates-catalog" in flags and not allow_duplicate:
        parts.append(f"candidate duplicates an existing catalog entry; pass --allow-duplicate {cid} to write anyway")
    if "overrides-bundled" in flags and not allow_override:
        parts.append(f"candidate overrides bundled byte-stack asset; pass --override-bundled {cid} to write anyway")
    return "; ".join(parts) or None


def _unified_diff(existing_norm, rendered, target_rel, exists):
    return "".join(
        difflib.unified_diff(
            existing_norm.splitlines(keepends=True), rendered.splitlines(keepends=True),
            fromfile="/dev/null" if not exists else f"a/{target_rel}", tofile=f"b/{target_rel}",
        )
    )


def _plan_candidate(cand, repo, bmode_assets, capture_py, dedupe_ctx, update_ids, force_ids, override_ids, dup_ids):
    """Dry-run one candidate, returning (exit_code, plan_dict, error_message)."""
    cid, kind, key = cand["id"], cand["kind"], cand["key"]
    parts = bmode_assets.validate_key(kind, key)
    target_rel = f".byte-stack/{kind}/{key}"
    allow_update, allow_force, allow_override, allow_dup = cid in update_ids, cid in force_ids, cid in override_ids, cid in dup_ids
    base_plan = {"category": cand["category"], "id": cid, "key": key, "kind": kind, "provenance": cand["provenance"], "relative_path": target_rel}

    if kind in ("playbooks", "workflows"):
        full_payload = {"schema_version": SCHEMA_VERSION, "kind": kind, "key": key, **cand["payload"]}
        proc = _run_capture_subprocess(capture_py, _capture_write_args(repo, dry_run=True, allow_update=allow_update, allow_force=allow_force), stdin_text=json.dumps(full_payload))
        if proc.returncode in (1, 2):
            return proc.returncode, None, (proc.stderr.strip() or proc.stdout.strip())
        try:
            cap_res = json.loads(proc.stdout)
        except ValueError as err:
            return 2, None, f"capture_playbook.py returned non-JSON: {err}"

        status, plan_code = cap_res["status"], proc.returncode
        dedupe = evaluate_dedupe(cand, status != "create", status == "unchanged", None, None, dedupe_ctx)
        diff, plan_reason = cap_res.get("diff", ""), cap_res.get("reason", "")
        will_write = status in ("create", "update", "force-overwrite") and plan_code == 0
        if status != "unchanged":
            blocking = _blocking_dedupe_reason(cid, dedupe["dedupe_flags"], allow_override, allow_dup)
            if blocking is not None:
                if plan_code == 3 and plan_reason:
                    plan_reason = f"{plan_reason}; {blocking}"
                else:
                    status, plan_code, will_write, plan_reason = "conflict", 3, False, blocking
        return plan_code, {
            **base_plan, "dedupe_flags": dedupe["dedupe_flags"], "diff": diff, "full_payload": full_payload,
            "reason": plan_reason or dedupe["reason"], "similar_to": dedupe["similar_to"], "status": status,
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
    ref_trigger = _inspect_markdown_head(rendered, key, bmode_assets)[0] if kind == "references" else ""
    dedupe = evaluate_dedupe(cand, exists, is_identical, rendered_bytes, rendered, dedupe_ctx, ref_trigger)
    existing_norm = existing_bytes.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n") if exists else ""
    diff = _unified_diff(existing_norm, rendered, target_rel, exists)
    line_endings_only = exists and not is_identical and existing_norm == rendered
    if exists and not is_identical and not diff:
        note = "line endings differ (existing file uses CR/CRLF; candidate uses LF)" if line_endings_only else "file bytes differ"
        diff = f"--- a/{target_rel}\n+++ b/{target_rel}\n@@ {note} @@\n"

    verdict_reason = dedupe["reason"].replace("differs", "differs (line endings differ)", 1) if line_endings_only else dedupe["reason"]
    blocking = _blocking_dedupe_reason(cid, dedupe["dedupe_flags"], allow_override, allow_dup)
    if not exists:
        status, plan_code, will_write, plan_reason = ("conflict", 3, False, blocking) if blocking else ("create", 0, True, f"new {kind[:-1]}")
    elif is_identical:
        status, plan_code, will_write, diff, plan_reason = "unchanged", 0, False, "", "already up to date"
    else:
        eol_note = " (line endings differ)" if line_endings_only else ""
        file_block = None if allow_force else f"refusing to overwrite differing {target_rel}{eol_note} without --force {cid}"
        if file_block is None and blocking is None:
            status, plan_code, will_write, plan_reason = "force-overwrite", 0, True, f"forced overwrite of existing {target_rel}{eol_note}"
        else:
            status, plan_code, will_write, plan_reason = "conflict", 3, False, "; ".join(p for p in (file_block, blocking) if p)

    return plan_code, {
        **base_plan, "content_sha256": hashlib.sha256(rendered_bytes).hexdigest(), "dedupe_flags": dedupe["dedupe_flags"],
        "diff": diff, "executable": cand.get("executable", False), "expected_bytes": existing_bytes, "parts": parts,
        "reason": plan_reason, "rendered": rendered, "similar_to": dedupe["similar_to"], "status": status,
        "title": _extract_h1(rendered) if kind == "references" else "", "trigger": ref_trigger, "verdict": dedupe["verdict"],
        "verdict_reason": verdict_reason, "will_write": will_write,
    }, None


def _public_plan_item(plan, *, written=False, validated=None, resolved_origin=None):
    item = {k: plan[k] for k in PUBLIC_PLAN_KEYS}
    item["written"] = written
    if validated is not None:
        item["validated"] = validated
    if resolved_origin is not None:
        item["resolved_origin"] = resolved_origin
    return item


def cmd_write(args):
    ctx = _init_worktree(args)
    if ctx is None:
        return 2
    repo, bmode_dir, bmode_assets, bmode_capture, capture_py, tracked, sanitizer = ctx
    tracked_map = dict(tracked)

    try:
        data = json.loads(sys.stdin.read() if args.stdin else args.candidates.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        return _emit_invalid([f"invalid candidates JSON: {err}"], args.json, sanitizer)

    errors = validate_candidates_envelope(data, repo, tracked_map, bmode_assets, bmode_capture)
    approve_ids, update_ids, force_ids, override_ids, dup_ids = (
        set(args.approve), set(args.update), set(args.force), set(args.override_bundled), set(args.allow_duplicate)
    )
    if not args.dry_run and not approve_ids:
        errors.append("at least one --approve ID is required unless --dry-run is set")

    candidates = data.get("candidates", []) if isinstance(data, dict) and isinstance(data.get("candidates"), list) else []
    known_ids = {c["id"] for c in candidates if isinstance(c, dict) and isinstance(c.get("id"), str)}
    for flag, id_set in (("--approve", approve_ids), ("--update", update_ids), ("--force", force_ids), ("--override-bundled", override_ids), ("--allow-duplicate", dup_ids)):
        if id_set - known_ids:
            errors.append(f"unknown candidate ID(s) in {flag}: {', '.join(sorted(id_set - known_ids))}")

    selected = []
    if not errors:
        selected = [c for c in candidates if (c["id"] in approve_ids) or (args.dry_run and not approve_ids)]
        targets = {(c["kind"], *bmode_assets.validate_key(c["kind"], c["key"])): c["id"] for c in selected}
        for t_parts, cid in sorted(targets.items()):
            for depth in range(2, len(t_parts)):
                if t_parts[:depth] in targets:
                    errors.append(f"target path collision: '{targets[t_parts[:depth]]}' cannot be both a file and parent directory of '{cid}'")
    if errors:
        return _emit_invalid(errors, args.json, sanitizer)

    try:
        dedupe_ctx = build_dedupe_context(repo, tracked_map, bmode_dir, bmode_assets)
    except (DiagnosticError, OSError, ValueError) as err:
        _emit(str(err), sanitizer, stream=sys.stderr)
        return 2

    planned = []
    for cand in selected:
        code, plan, err_msg = _plan_candidate(cand, repo, bmode_assets, capture_py, dedupe_ctx, update_ids, force_ids, override_ids, dup_ids)
        if code in (1, 2):
            msg = err_msg or "preflight failed"
            return _emit_invalid([msg], True, sanitizer) if (args.json and code == 1) else (_emit(msg, sanitizer, stream=sys.stderr) or code)
        if code == 0 and plan["status"] != "unchanged":
            dedupe_ctx["catalog_entries"].append({
                "origin": "batch", "kind": plan["kind"], "key": plan["key"], "trigger": plan["trigger"],
                "title": plan["title"], "content_sha256": plan.get("content_sha256"),
                "tokens": _catalog_tokens(plan["kind"], plan["title"], plan["trigger"]),
            })
        planned.append((code, plan))

    results, had_conflict = [], False
    for code, plan in planned:
        if args.dry_run or code == 3 or not plan["will_write"]:
            had_conflict = had_conflict or code == 3
            results.append(_public_plan_item(plan, written=False))
            continue
        cid, kind, key = plan["id"], plan["kind"], plan["key"]
        validated, real_plan, did_write = None, plan, True
        if kind in ("playbooks", "workflows"):
            proc = _run_capture_subprocess(capture_py, _capture_write_args(repo, dry_run=False, allow_update=cid in update_ids, allow_force=cid in force_ids), stdin_text=json.dumps(plan["full_payload"]))
            if proc.returncode not in (0, 3):
                _emit(proc.stderr.strip() or proc.stdout.strip(), sanitizer, stream=sys.stderr)
                return proc.returncode
            try:
                cap_res = json.loads(proc.stdout)
            except ValueError as err:
                if proc.returncode == 3:
                    had_conflict = True
                    results.append(_public_plan_item(dict(plan, status="conflict", reason=proc.stderr.strip() or proc.stdout.strip() or "target conflicted during write"), written=False))
                    continue
                _emit(f"capture_playbook.py returned non-JSON: {err}", sanitizer, stream=sys.stderr)
                return 2
            if proc.returncode == 3:
                had_conflict = True
                results.append(_public_plan_item(dict(plan, status="conflict", reason=cap_res.get("reason", "target conflicted during write"), diff=cap_res.get("diff", "")), written=False))
                continue
            real_status = cap_res.get("status", plan["status"])
            did_write = real_status in ("create", "update", "force-overwrite")
            real_plan = dict(plan, status=real_status, diff=cap_res.get("diff", ""), reason=cap_res.get("reason", plan["reason"]))
            val_proc = subprocess.run([sys.executable, "-I", str(capture_py), "validate", f".byte-stack/{kind}/{key}", "--kind", kind, "--json"], cwd=str(repo), capture_output=True, text=True)
            if val_proc.returncode != 0:
                _emit(f"post-write validation failed for {cid}: {val_proc.stderr.strip() or val_proc.stdout.strip()}", sanitizer, stream=sys.stderr)
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
                        late_plan["diff"] = _unified_diff(target.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n"), plan["rendered"], plan["relative_path"], True)
                except OSError:
                    pass
                results.append(_public_plan_item(late_plan, written=False))
                continue
            except (DiagnosticError, OSError, ValueError) as err:
                _emit(str(err), sanitizer, stream=sys.stderr)
                return 2

        origin, _ = bmode_assets.resolve(repo, kind, key, bmode_dir)
        if origin != "repo":
            _emit(f"post-write resolve did not return repo for {cid}", sanitizer, stream=sys.stderr)
            return 2
        results.append(_public_plan_item(real_plan, written=did_write, validated=validated, resolved_origin=origin))

    exit_code = 3 if had_conflict else 0
    if args.json:
        _emit({"dry_run": args.dry_run, "results": results, "schema_version": SCHEMA_VERSION, "status": "conflict" if had_conflict else "ok"}, sanitizer, as_json=True)
    else:
        clean_results, out_lines, prefix = _sanitize_value(results, sanitizer), [], ("dry-run " if args.dry_run else "")
        for item in clean_results:
            out_lines.append(f"{prefix}{item['status']}: {item['relative_path']} [verdict={item['verdict']}] ({item['reason']})")
            if item["similar_to"]:
                out_lines.append("  similar_to: " + ", ".join(f"{s['source']} ({s['score']})" for s in item["similar_to"]))
            if item["diff"]:
                out_lines.append(item["diff"].rstrip("\n"))
        if out_lines:
            _emit("\n".join(out_lines), sanitizer)
    return exit_code


def cmd_schema():
    _emit(SCHEMA_PATH.read_text(encoding="utf-8"), _build_sanitizer(), end="")
    return 0


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        """Report a usage error through the output boundary, with every argument value taken out of the message."""
        values = {part for arg in sys.argv[1:] if arg not in self._option_string_actions for part in (arg, arg.split("=", 1)[-1])}
        for value in sorted((v for v in values if len(v) >= 4), key=len, reverse=True):
            message = message.replace(value, "<value>")
        _emit(f"{self.prog}: error: {message} (run with --help)", _build_sanitizer(), stream=sys.stderr)
        raise SystemExit(2)


def build_parser():
    top_common = _Parser(add_help=False)
    top_common.add_argument("--bmode", type=Path, default=None, help="Path to installed bmode skill directory (default: sibling ../bmode)")
    sub_common = _Parser(add_help=False)
    sub_common.add_argument("--bmode", type=Path, default=argparse.SUPPRESS, help="Path to installed bmode skill directory (default: sibling ../bmode)")

    parser = _Parser(description=__doc__, parents=[top_common])
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
    for flag, help_text in (
        ("--approve", "Candidate ID (kind/key) approved to write"),
        ("--update", "Candidate ID allowed to update an unmodified managed playbook/workflow"),
        ("--override-bundled", "Candidate ID allowed to override a bundled byte-stack asset"),
        ("--allow-duplicate", "Candidate ID allowed despite restates-steering or duplicates-catalog"),
        ("--force", "Candidate ID allowed to overwrite differing/manual files"),
    ):
        wr_p.add_argument(flag, action="append", default=[], metavar="ID", help=help_text)
    wr_p.add_argument("--json", action="store_true", help="Print structured JSON result")
    wr_p.add_argument("--cwd", type=Path, default=Path.cwd(), help="Directory inside target Git worktree")
    return parser


def main():
    args = build_parser().parse_args()
    return cmd_inventory(args) if args.command == "inventory" else (cmd_write(args) if args.command == "write" else cmd_schema())


if __name__ == "__main__":
    sys.exit(main())
