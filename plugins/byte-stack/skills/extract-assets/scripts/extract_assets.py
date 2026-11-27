#!/usr/bin/env python3
"""Scan a Git repository and deterministically preview/write .byte-stack/ assets."""
import argparse
import difflib
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
    {
        "id",
        "category",
        "kind",
        "key",
        "provenance",
        "rationale",
        "payload",
        "content",
        "executable",
    }
)
ALLOWED_PROVENANCE_KEYS = frozenset({"path", "command", "key", "line"})
ALLOWED_PAYLOAD_SUBKEYS = frozenset(
    {"title", "use_when", "prerequisites", "steps", "verification", "guardrails"}
)

REF_KEY_PATTERN = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*\.md$"
)
SCRIPT_KEY_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[-_][a-z0-9]+)*(?:/[a-z0-9]+(?:[-_][a-z0-9]+)*)*(?:\.[a-z0-9]+)?$"
)

MAX_CONTENT_BYTES = 65536
MAX_PROVENANCE_READ_BYTES = 1048576
DEFAULT_MAX_FILES = 100
DEFAULT_MAX_BYTES = 262144
MAX_SIGNALS_PER_FILE = 30
MAX_SIGNAL_TEXT_LEN = 200

VENDOR_BUILD_DIRS = frozenset(
    {
        "node_modules",
        "vendor",
        "third_party",
        "dist",
        "build",
        "target",
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        ".nox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".next",
        ".nuxt",
        ".cache",
        "coverage",
        "htmlcov",
        ".gradle",
        "Pods",
        "bower_components",
        ".terraform",
        ".eggs",
    }
)

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
    re.compile(r".+\.local\..+$", re.IGNORECASE),
    re.compile(r".+\.local$", re.IGNORECASE),
    re.compile(r"^(?:\.DS_Store|Thumbs\.db|Desktop\.ini)$", re.IGNORECASE),
    re.compile(r".+\.(?:swp|swo)$", re.IGNORECASE),
    re.compile(r".+~$"),
)

STEERING_NAMES = frozenset(
    {"agents.md", "claude.md", "gemini.md", "codex.md", "copilot.md"}
)
DIRECTIVE_NAMES = frozenset(
    {
        "contributing.md",
        "glossary.md",
        "standards.md",
        "conventions.md",
        "style.md",
        "styleguide.md",
        "style-guide.md",
        "scripts.md",
        "code_of_conduct.md",
        "security.md",
    }
)
TASK_RUNNER_NAMES = frozenset(
    {
        "makefile",
        "gnumakefile",
        "justfile",
        "taskfile.yml",
        "taskfile.yaml",
        "package.json",
        "pyproject.toml",
        "setup.cfg",
        "tox.ini",
        "noxfile.py",
        "cargo.toml",
        "go.mod",
        "rakefile",
        "turbo.json",
        "nx.json",
        "mise.toml",
        "procfile",
    }
)
QUALITY_EXACT_NAMES = frozenset(
    {
        ".editorconfig",
        ".flake8",
        ".pylintrc",
        "pylintrc",
        ".isort.cfg",
        ".bandit",
        ".shellcheckrc",
        ".hadolint.yaml",
        "biome.json",
        "biome.jsonc",
        "pyrightconfig.json",
        "jsconfig.json",
        "oxlint.json",
        ".oxlintrc.json",
        "deno.json",
        "renovate.json",
        "ruff.toml",
        ".ruff.toml",
        "mypy.ini",
        ".mypy.ini",
        ".golangci.yml",
        ".golangci.yaml",
        "rustfmt.toml",
        ".rustfmt.toml",
        "clippy.toml",
        ".clippy.toml",
        "tsconfig.json",
    }
)
QUALITY_PREFIXES = (
    ".eslintrc",
    "eslint.config.",
    ".prettierrc",
    "prettier.config.",
    "tsconfig.",
    ".stylelintrc",
    ".markdownlint",
    ".yamllint",
)
SCRIPT_DIRS = frozenset({"scripts", "script", "bin", "tools"})
SCRIPT_EXTS = frozenset(
    {".sh", ".bash", ".zsh", ".py", ".ts", ".js", ".mjs", ".cjs", ".rb", ".pl", ".ps1"}
)
STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "use",
        "when",
        "run",
        "file",
        "files",
        "repo",
        "repository",
        "are",
        "not",
        "all",
        "any",
        "only",
        "into",
        "before",
        "after",
        "check",
        "steps",
        "verification",
    }
)


class DiagnosticError(Exception):
    """Error resulting in exit code 2 (missing bmode, Git, path, or symlink guard)."""


def load_bmode(bmode_arg):
    """Locate and import bmode's assets and capture_playbook modules."""
    bmode_dir = (bmode_arg if bmode_arg is not None else DEFAULT_BMODE).resolve()
    skill_md = bmode_dir / "SKILL.md"
    assets_py = bmode_dir / "scripts" / "assets.py"
    capture_py = bmode_dir / "scripts" / "capture_playbook.py"
    if not skill_md.is_file() or not assets_py.is_file() or not capture_py.is_file():
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


def _sanitize_text(text, repo, bmode_dir, bmode_capture):
    """Remove absolute repo/bmode paths and local home paths from diagnostics."""
    out = text
    candidates = []
    if repo is not None:
        candidates.extend([str(repo.resolve()), str(repo)])
    if bmode_dir is not None:
        candidates.extend([str(bmode_dir.resolve()), str(bmode_dir)])
    for needle in sorted(set(candidates), key=len, reverse=True):
        if needle:
            replacement = "<repo>" if repo is not None and needle in (str(repo), str(repo.resolve())) else "<bmode>"
            out = out.replace(needle, replacement)
    for pat in bmode_capture.LOCAL_PATH_PATTERNS:
        out = pat.sub("<local-path>/", out)
    return out


def _contains_sensitive(text, bmode_capture, repo_strings=()):
    for needle in repo_strings:
        if needle and needle in text:
            return True
    for pat in bmode_capture.LOCAL_PATH_PATTERNS:
        if pat.search(text):
            return True
    for pat in bmode_capture.SECRET_PATTERNS:
        if pat.search(text):
            return True
    return False


def _check_safety_patterns(bmode_capture, label, text, errors):
    for pat in bmode_capture.LOCAL_PATH_PATTERNS:
        if pat.search(text):
            errors.append(f"{label} must not contain a machine-local home path")
            break
    for pat in bmode_capture.SECRET_PATTERNS:
        if pat.search(text):
            errors.append(f"{label} appears to contain a secret or credential")
            break


def _check_existing_path_is_regular(path):
    if path.is_symlink():
        raise ValueError(f"symlink in asset path: {path}")
    if path.exists() and not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"expected regular file: {path}")


def list_tracked_files(repo):
    """Return sorted list of (rel_posix_path, mode) from `git ls-files -s -z`."""
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-s", "-z"],
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
    )
    if result.returncode != 0:
        raise DiagnosticError(result.stderr.strip() or "git ls-files failed")
    seen = {}
    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        if "\t" not in entry:
            continue
        meta, rel_path = entry.split("\t", 1)
        parts = meta.split()
        if not parts:
            continue
        mode = parts[0]
        if rel_path not in seen:
            seen[rel_path] = mode
    return sorted(seen.items(), key=lambda item: item[0])


def exclusion_reason(rel_path, mode):
    """Return exclusion reason string for a tracked entry, or None if allowed."""
    if mode == "120000":
        return "symlink"
    if mode == "160000":
        return "submodule"
    parts = rel_path.split("/")
    if any(part in VENDOR_BUILD_DIRS for part in parts[:-1]):
        return "vendored_or_build"
    name = parts[-1]
    for pat in SECRET_NAME_PATTERNS:
        if pat.search(name):
            return "secret_file"
    for pat in MACHINE_LOCAL_PATTERNS:
        if pat.search(name):
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

    # 1. CI pipelines
    if (
        (len(parts) >= 3 and parts[0] == ".github" and parts[1] == "workflows" and suffix in (".yml", ".yaml"))
        or lower_path in (".gitlab-ci.yml", ".gitlab-ci.yaml", ".circleci/config.yml", ".circleci/config.yaml",
                          "jenkinsfile", "azure-pipelines.yml", "azure-pipelines.yaml",
                          ".travis.yml", "bitbucket-pipelines.yml")
        or (len(parts) >= 2 and parts[0] == ".buildkite" and suffix in (".yml", ".yaml"))
    ):
        return "ci"

    # 2. Git hooks
    if (
        lower_path in (".pre-commit-config.yaml", ".pre-commit-config.yml",
                       ".lefthook.yml", "lefthook.yml", "lefthook.yaml", ".gitattributes")
        or (parts[0] == ".husky" and len(parts) == 2 and not lower_name.startswith("_"))
        or (parts[0] in (".githooks", "githooks") and len(parts) >= 2)
        or lower_name.startswith(".lintstagedrc")
        or lower_name.startswith("lint-staged.config.")
    ):
        return "git_hooks"

    # 3. Steering files
    if (
        lower_name in STEERING_NAMES
        or lower_path in (".github/copilot-instructions.md", ".cursorrules", ".claude/settings.json")
        or lower_path.startswith(".cursor/rules/")
    ):
        return "steering"

    # 4. ADRs
    if suffix in (".md", ".mdx") and (
        lower_path.startswith("docs/adr/")
        or lower_path.startswith("docs/adrs/")
        or lower_path.startswith("docs/decisions/")
        or lower_path.startswith("adr/")
        or lower_path.startswith("adrs/")
    ):
        return "adrs"

    # 5. Directives and contribution guides
    if (
        (
            lower_path.startswith("docs/directives/")
            or lower_path.startswith("docs/standards/")
            or lower_path.startswith("docs/guidelines/")
            or lower_path.startswith("docs/policies/")
        )
        and suffix in (".md", ".mdx", ".txt")
    ) or lower_name in DIRECTIVE_NAMES or lower_path in (
        "docs/standards.md",
        "docs/conventions.md",
        "docs/style-guide.md",
        "docs/styleguide.md",
        "docs/workflow.md",
        "docs/contributing.md",
        ".github/contributing.md",
    ):
        return "directives"

    # 6. Linter, formatter, typechecker configs
    if (
        lower_name in QUALITY_EXACT_NAMES
        or any(lower_name.startswith(pref) for pref in QUALITY_PREFIXES)
        or lower_path in (".github/dependabot.yml", ".github/dependabot.yaml")
    ):
        return "quality"

    # 7. Task runners and package manifests
    if (
        lower_name in TASK_RUNNER_NAMES
        or suffix == ".mk"
        or lower_name.startswith("gruntfile.")
        or lower_name.startswith("gulpfile.")
    ):
        return "task_runners"

    # 8. Scripts
    if parts[0] in SCRIPT_DIRS and (suffix in SCRIPT_EXTS or mode == "100755"):
        return "scripts"

    return None


def _clip_signal(text):
    collapsed = " ".join(text.strip().split())
    if len(collapsed) > MAX_SIGNAL_TEXT_LEN:
        return collapsed[: MAX_SIGNAL_TEXT_LEN - 3] + "..."
    return collapsed


def extract_signals(rel_path, text, bmode_capture, repo_strings):
    """Extract bounded signals (commands, keys, headings) with 1-based line numbers."""
    signals = []
    truncated_signals = False
    dropped_sensitive = 0
    lines = text.splitlines()
    lower_name = Path(rel_path).name.lower()
    suffix = Path(lower_name).suffix

    def add_signal(kind, line_no, raw_text):
        nonlocal truncated_signals, dropped_sensitive
        if _contains_sensitive(raw_text, bmode_capture, repo_strings):
            dropped_sensitive += 1
            return
        clipped = _clip_signal(raw_text)
        if not clipped:
            return
        if len(signals) >= MAX_SIGNALS_PER_FILE:
            truncated_signals = True
            return
        signals.append({"kind": kind, "line": line_no, "text": clipped})

    if suffix in (".md", ".mdx"):
        in_fence = False
        fence_shell = False
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("```"):
                if not in_fence:
                    lang = stripped[3:].strip().lower().split()[0] if stripped[3:].strip() else ""
                    in_fence = True
                    fence_shell = lang in ("sh", "bash", "shell", "zsh", "console", "")
                else:
                    in_fence = False
                    fence_shell = False
                continue
            if not in_fence and re.match(r"^#{1,4}\s+\S", stripped):
                add_signal("heading", idx, stripped)
            elif in_fence and fence_shell and stripped and not stripped.startswith("#"):
                add_signal("command", idx, stripped.lstrip("$ ").strip() if stripped.startswith("$ ") else stripped)
    elif suffix in (".json", ".jsonc"):
        if lower_name == "package.json":
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                scripts_obj = parsed.get("scripts")
                if isinstance(scripts_obj, dict):
                    for sname in sorted(scripts_obj.keys()):
                        sval = scripts_obj[sname]
                        if isinstance(sval, str):
                            line_no = _find_line(lines, f'"{sname}"')
                            add_signal("command", line_no, f"{sname}: {sval}")
                for k in sorted(parsed.keys()):
                    if k != "scripts":
                        add_signal("key", _find_line(lines, f'"{k}"'), k)
            else:
                _extract_json_keys_regex(lines, add_signal)
        else:
            _extract_json_keys_regex(lines, add_signal)
    elif suffix in (".yml", ".yaml"):
        in_run_block = False
        run_indent = 0
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
                    in_run_block = True
                    run_indent = indent
                elif val:
                    add_signal("command", idx, val)
                continue
            m_uses = re.match(r"^\s*(?:-\s*)?(?:uses|repo|id):\s*(.+)$", line)
            if m_uses:
                add_signal("key", idx, m_uses.group(0).strip())
                continue
            if indent == 0:
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
        in_scripts = False
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";")):
                continue
            m_sec = re.match(r"^\[([^\]]+)\]$", stripped)
            if m_sec:
                sec = m_sec.group(1).strip()
                add_signal("key", idx, sec)
                in_scripts = sec.endswith("scripts")
                continue
            if "=" in stripped:
                k, v = stripped.split("=", 1)
                k = k.strip()
                v = v.strip()
                if in_scripts:
                    add_signal("command", idx, f"{k} = {v}")
                elif not line.startswith((" ", "\t")):
                    add_signal("key", idx, k)
    else:
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue
            if idx == 1 and stripped.startswith("#!"):
                add_signal("heading", idx, stripped)
            elif re.match(r"^(?:def|async def|function|export function)\s+[A-Za-z0-9_-]+", stripped):
                add_signal("key", idx, stripped.split("{")[0].rstrip(":"))
            elif idx <= 5 and stripped.startswith(("# ", "// ", '"""')):
                add_signal("heading", idx, stripped.lstrip("#/ \""))
            elif re.match(r"^(?:python3?|node|npm|pnpm|yarn|pytest|go|cargo|git|make|bash|sh|rg)\s+\S", stripped):
                add_signal("command", idx, stripped)

    return signals, truncated_signals, dropped_sensitive


def _find_line(lines, needle):
    for idx, line in enumerate(lines, 1):
        if needle in line:
            return idx
    return 1


def _extract_json_keys_regex(lines, add_signal):
    for idx, line in enumerate(lines, 1):
        m = re.match(r'^\s{1,2}"([^"]+)"\s*:', line)
        if m:
            add_signal("key", idx, m.group(1))


def read_bundled_catalog(bmode_assets, bmode_dir, kind):
    """Read only bundled bmode entries for one kind without touching repo .byte-stack."""
    base = bmode_dir / kind
    entries = {}
    if not base.is_dir():
        return entries
    for path in sorted(base.rglob("*")):
        key = path.relative_to(base)
        if any(part.startswith(".") or part == "__pycache__" for part in key.parts):
            continue
        if path.is_dir() or (kind in ("playbooks", "workflows") and path.suffix != ".md"):
            continue
        trigger = bmode_assets.inspect_file(path, kind)
        entries[key.as_posix()] = trigger
    return entries


def collect_byte_stack_inventory(repo, bmode_dir, bmode_assets, bmode_capture):
    """Inspect bundled and repo .byte-stack catalogs across all four kinds."""
    catalog_out = {}
    diagnostics = []
    for kind in bmode_assets.KINDS:
        bundled = read_bundled_catalog(bmode_assets, bmode_dir, kind)
        entries = []
        try:
            merged = bmode_assets.catalog(repo, kind, bmode_dir)
            for key, trigger in sorted(merged.items()):
                origin, _ = bmode_assets.resolve(repo, kind, key, bmode_dir)
                item = {
                    "key": key,
                    "origin": origin,
                    "overrides_bundled": origin == "repo" and key in bundled,
                    "trigger": trigger,
                }
                if origin == "repo":
                    item["repo_path"] = f".byte-stack/{kind}/{key}"
                entries.append(item)
        except (OSError, ValueError) as err:
            diagnostics.append(
                {
                    "kind": kind,
                    "message": _sanitize_text(str(err), repo, bmode_dir, bmode_capture),
                    "scope": "byte_stack",
                }
            )
            for key, trigger in sorted(bundled.items()):
                entries.append(
                    {
                        "key": key,
                        "origin": "bundled",
                        "overrides_bundled": False,
                        "trigger": trigger,
                    }
                )
        catalog_out[kind] = entries
    diagnostics.sort(key=lambda d: (d["scope"], d["kind"], d["message"]))
    return catalog_out, diagnostics


def cmd_inventory(args):
    if args.max_files < 1 or args.max_bytes < 1:
        print("--max-files and --max-bytes must be positive integers", file=sys.stderr)
        return 1

    try:
        bmode_dir, bmode_assets, bmode_capture, _ = load_bmode(args.bmode)
        repo = bmode_assets.checkout(args.cwd)
        if repo is None:
            raise DiagnosticError("Run extract-assets inside a Git worktree.")
        tracked = list_tracked_files(repo)
    except (DiagnosticError, OSError, ValueError) as err:
        print(str(err), file=sys.stderr)
        return 2

    repo_strings = tuple(sorted({str(repo), str(repo.resolve())}, key=len, reverse=True))
    categories = {
        "adrs": [],
        "ci": [],
        "directives": [],
        "git_hooks": [],
        "quality": [],
        "scripts": [],
        "steering": [],
        "task_runners": [],
    }
    exclusions = {}
    truncated = {"bytes": False, "files": False, "signals": False}
    unclassified_count = 0
    files_read = 0
    bytes_remaining = args.max_bytes

    def bump_exclusion(reason, count=1):
        if count > 0:
            exclusions[reason] = exclusions.get(reason, 0) + count

    for rel_path, mode in tracked:
        reason = exclusion_reason(rel_path, mode)
        if reason is not None:
            bump_exclusion(reason)
            continue
        bucket = classify_path(rel_path, mode)
        if bucket is None:
            if not rel_path.startswith(".byte-stack/"):
                unclassified_count += 1
            continue
        if files_read >= args.max_files:
            truncated["files"] = True
            bump_exclusion("max_files_limit")
            continue
        if bytes_remaining <= 0:
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
        except OSError:
            bump_exclusion("unreadable")
            continue
        if not stat.S_ISREG(st.st_mode):
            bump_exclusion("non_regular_file")
            continue

        try:
            with target.open("rb") as handle:
                raw = handle.read(bytes_remaining)
        except OSError:
            bump_exclusion("unreadable")
            continue

        if b"\x00" in raw:
            bump_exclusion("binary")
            continue

        files_read += 1
        file_size = st.st_size
        bytes_read = len(raw)
        bytes_remaining -= bytes_read
        file_truncated = bytes_read < file_size
        if file_truncated:
            truncated["bytes"] = True

        text = raw.decode("utf-8", errors="replace")
        signals, sig_truncated, dropped_sensitive = extract_signals(
            rel_path, text, bmode_capture, repo_strings
        )
        if sig_truncated:
            file_truncated = True
            truncated["signals"] = True
        bump_exclusion("sensitive_signals_dropped", dropped_sensitive)

        categories[bucket].append(
            {
                "bytes": file_size,
                "bytes_read": bytes_read,
                "lines": len(text.splitlines()),
                "path": rel_path,
                "signals": signals,
                "truncated": file_truncated,
            }
        )

    for bucket in categories:
        categories[bucket].sort(key=lambda item: item["path"])

    byte_stack_catalog, diagnostics = collect_byte_stack_inventory(
        repo, bmode_dir, bmode_assets, bmode_capture
    )

    output = {
        "byte_stack": byte_stack_catalog,
        "categories": categories,
        "diagnostics": diagnostics,
        "exclusions": dict(sorted(exclusions.items())),
        "limits": {
            "max_bytes": args.max_bytes,
            "max_files": args.max_files,
            "max_signals_per_file": MAX_SIGNALS_PER_FILE,
        },
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "bytes_read": args.max_bytes - bytes_remaining,
            "files_read": files_read,
            "tracked_files": len(tracked),
            "unclassified_tracked_files": unclassified_count,
        },
        "truncated": truncated,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def _normalize_lf(text):
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def _normalize_ws(text):
    return " ".join(text.split())


def _normalize_title_or_trigger(text):
    return _normalize_ws(text).lower().rstrip(".:")


def _extract_h1(text):
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _tokenize(text):
    words = re.findall(r"[a-z0-9]{3,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def _candidate_text_for_tokens(candidate):
    if candidate["kind"] in ("playbooks", "workflows"):
        p = candidate["payload"]
        parts = [p.get("title", ""), p.get("use_when", "")]
        for field in ("prerequisites", "steps", "verification", "guardrails"):
            parts.extend(p.get(field, []))
        return "\n".join(parts)
    return candidate["content"]


def _candidate_lines_for_steering(candidate):
    lines = []
    if candidate["kind"] in ("playbooks", "workflows"):
        p = candidate["payload"]
        if p.get("title"):
            lines.append(p["title"].strip())
        if p.get("use_when"):
            lines.append(p["use_when"].strip())
        for field in ("prerequisites", "steps", "verification", "guardrails"):
            for item in p.get(field, []):
                stripped = item.strip()
                if stripped:
                    lines.append(stripped)
    else:
        for raw in _normalize_lf(candidate["content"]).splitlines():
            stripped = raw.strip()
            if not stripped or stripped == "---":
                continue
            lines.append(stripped)
    return lines


def _strip_bullet(line):
    return re.sub(r"^(?:[-*+]|\d+\.)\s+", "", line.strip()).strip()


def validate_candidates_envelope(data, repo, tracked_map, bmode_assets, bmode_capture):
    """Validate candidate envelope, per-kind rules, safety patterns, and provenance."""
    if not isinstance(data, dict):
        return ["candidates input must be a JSON object"]

    errors = []
    unknown_env = sorted(set(data.keys()) - ALLOWED_ENVELOPE_KEYS)
    if unknown_env:
        errors.append(f"unknown envelope field(s): {', '.join(unknown_env)}")
    if "schema_version" not in data:
        errors.append("missing required field: schema_version")
    else:
        sv = data["schema_version"]
        if isinstance(sv, bool) or not isinstance(sv, int) or sv != SCHEMA_VERSION:
            errors.append(f"schema_version must be integer {SCHEMA_VERSION}")

    if "candidates" not in data:
        errors.append("missing required field: candidates")
        return errors
    candidates = data["candidates"]
    if not isinstance(candidates, list):
        errors.append("candidates must be an array")
        return errors
    if len(candidates) > 50:
        errors.append("candidates must contain at most 50 items")

    seen_ids = set()
    file_cache = {}

    def read_provenance_file(rel_path):
        if rel_path in file_cache:
            return file_cache[rel_path]
        target = bmode_assets.checked(repo, rel_path.split("/"))
        _check_existing_path_is_regular(target)
        if not target.exists():
            raise ValueError(f"missing file in worktree: {rel_path}")
        with target.open("rb") as handle:
            raw = handle.read(MAX_PROVENANCE_READ_BYTES)
        text = raw.decode("utf-8", errors="replace")
        entry = (text, text.splitlines(), _normalize_ws(text))
        file_cache[rel_path] = entry
        return entry

    for idx, cand in enumerate(candidates):
        prefix = f"candidates[{idx}]"
        if not isinstance(cand, dict):
            errors.append(f"{prefix} must be an object")
            continue

        unknown_c = sorted(set(cand.keys()) - ALLOWED_CANDIDATE_KEYS)
        if unknown_c:
            errors.append(f"{prefix} has unknown field(s): {', '.join(unknown_c)}")

        for req in ("id", "category", "kind", "key", "provenance"):
            if req not in cand:
                errors.append(f"{prefix} missing required field: {req}")

        category = cand.get("category")
        if "category" in cand and (not isinstance(category, str) or category not in ALLOWED_CATEGORIES):
            errors.append(f"{prefix}.category must be one of: {', '.join(ALLOWED_CATEGORIES)}")

        kind = cand.get("kind")
        if "kind" in cand and (not isinstance(kind, str) or kind not in ALLOWED_KINDS):
            errors.append(f"{prefix}.kind must be one of: {', '.join(ALLOWED_KINDS)}")

        key = cand.get("key")
        if "key" in cand:
            if not isinstance(key, str):
                errors.append(f"{prefix}.key must be a string")
            else:
                _check_safety_patterns(bmode_capture, f"{prefix}.key", key, errors)
                if kind in ALLOWED_KINDS:
                    try:
                        bmode_assets.validate_key(kind, key)
                    except ValueError as err:
                        errors.append(f"{prefix}.key: {err}")
                    if kind in ("playbooks", "workflows"):
                        if not (4 <= len(key) <= 120) or not bmode_capture.KEY_PATTERN.fullmatch(key):
                            errors.append(
                                f"{prefix}.key must be lowercase kebab-case path ending in .md (4..120 chars)"
                            )
                    elif kind == "references":
                        if not (4 <= len(key) <= 120) or not REF_KEY_PATTERN.fullmatch(key):
                            errors.append(
                                f"{prefix}.key must be lowercase kebab-case path ending in .md (4..120 chars)"
                            )
                    elif kind == "scripts":
                        if not (2 <= len(key) <= 120) or not SCRIPT_KEY_PATTERN.fullmatch(key):
                            errors.append(
                                f"{prefix}.key must be lowercase path (2..120 chars, alphanumeric/-/_ with optional extension)"
                            )

        cid = cand.get("id")
        if "id" in cand:
            if not isinstance(cid, str) or not cid.strip():
                errors.append(f"{prefix}.id must be a non-empty string")
            else:
                if kind in ALLOWED_KINDS and isinstance(key, str) and cid != f"{kind}/{key}":
                    errors.append(f"{prefix}.id must equal '{kind}/{key}'")
                if cid in seen_ids:
                    errors.append(f"duplicate candidate id: {cid}")
                seen_ids.add(cid)

        if "rationale" in cand:
            rat = cand["rationale"]
            if not isinstance(rat, str) or not (3 <= len(rat.strip()) <= 400):
                errors.append(f"{prefix}.rationale must be a string (3..400 chars)")
            else:
                _check_safety_patterns(bmode_capture, f"{prefix}.rationale", rat, errors)

        if "executable" in cand:
            if not isinstance(cand["executable"], bool):
                errors.append(f"{prefix}.executable must be a boolean")
            elif kind in ALLOWED_KINDS and kind != "scripts":
                errors.append(f"{prefix}.executable is only allowed when kind is 'scripts'")

        # Provenance validation
        prov_list = cand.get("provenance")
        if "provenance" in cand:
            if not isinstance(prov_list, list) or not (1 <= len(prov_list) <= 20):
                errors.append(f"{prefix}.provenance must be a non-empty array (1..20 items)")
            else:
                for pidx, prov in enumerate(prov_list):
                    p_label = f"{prefix}.provenance[{pidx}]"
                    if not isinstance(prov, dict):
                        errors.append(f"{p_label} must be an object")
                        continue
                    unknown_p = sorted(set(prov.keys()) - ALLOWED_PROVENANCE_KEYS)
                    if unknown_p:
                        errors.append(f"{p_label} has unknown field(s): {', '.join(unknown_p)}")
                    ppath = prov.get("path")
                    if not isinstance(ppath, str) or not ppath.strip():
                        errors.append(f"{p_label}.path must be a non-empty string")
                        continue
                    _check_safety_patterns(bmode_capture, f"{p_label}.path", ppath, errors)
                    if ppath.startswith("/") or "\\" in ppath or ".." in ppath.split("/"):
                        errors.append(f"{p_label}.path must be a repo-relative POSIX path")
                        continue
                    if ppath not in tracked_map:
                        errors.append(f"{p_label}.path is not a tracked repository file: {ppath}")
                        continue
                    excl = exclusion_reason(ppath, tracked_map[ppath])
                    if excl is not None:
                        errors.append(f"{p_label}.path is excluded ({excl}): {ppath}")
                        continue
                    try:
                        file_text, file_lines, norm_text = read_provenance_file(ppath)
                    except (OSError, ValueError) as err:
                        errors.append(f"{p_label}.path unreadable or unsafe: {err}")
                        continue

                    if "line" in prov:
                        line_no = prov["line"]
                        if isinstance(line_no, bool) or not isinstance(line_no, int) or line_no < 1:
                            errors.append(f"{p_label}.line must be a positive integer")
                        elif line_no > len(file_lines):
                            errors.append(
                                f"{p_label}.line {line_no} exceeds {ppath} length ({len(file_lines)} lines)"
                            )

                    if "command" in prov:
                        cmd = prov["command"]
                        if not isinstance(cmd, str) or not cmd.strip() or len(cmd) > 400:
                            errors.append(f"{p_label}.command must be a non-empty string (<= 400 chars)")
                        else:
                            _check_safety_patterns(bmode_capture, f"{p_label}.command", cmd, errors)
                            if _normalize_ws(cmd) not in norm_text:
                                errors.append(f"{p_label}.command not found in {ppath}")

                    if "key" in prov:
                        pkey = prov["key"]
                        if not isinstance(pkey, str) or not pkey.strip() or len(pkey) > 200:
                            errors.append(f"{p_label}.key must be a non-empty string (<= 200 chars)")
                        else:
                            _check_safety_patterns(bmode_capture, f"{p_label}.key", pkey, errors)
                            segments = pkey.split(".")
                            if any(not seg for seg in segments):
                                errors.append(f"{p_label}.key contains empty dotted segment: {pkey}")
                            else:
                                missing = [seg for seg in segments if seg not in file_text]
                                if missing:
                                    errors.append(
                                        f"{p_label}.key segment(s) not found in {ppath}: {', '.join(missing)}"
                                    )

        # Kind-specific payload/content validation
        if kind in ("playbooks", "workflows"):
            if "content" in cand:
                errors.append(f"{prefix}.content is not allowed for {kind}; use payload")
            if "payload" not in cand:
                errors.append(f"{prefix}.payload is required for {kind}")
            elif not isinstance(cand["payload"], dict):
                errors.append(f"{prefix}.payload must be an object")
            else:
                payload = cand["payload"]
                unknown_pl = sorted(set(payload.keys()) - ALLOWED_PAYLOAD_SUBKEYS)
                if unknown_pl:
                    errors.append(f"{prefix}.payload has unknown field(s): {', '.join(unknown_pl)}")
                elif isinstance(key, str):
                    full_payload = {
                        "schema_version": SCHEMA_VERSION,
                        "kind": kind,
                        "key": key,
                        **payload,
                    }
                    for perr in bmode_capture.validate_payload(full_payload):
                        errors.append(f"{prefix}.payload: {perr}")
        elif kind in ("references", "scripts"):
            if "payload" in cand:
                errors.append(f"{prefix}.payload is not allowed for {kind}; use content")
            if "content" not in cand:
                errors.append(f"{prefix}.content is required for {kind}")
            elif not isinstance(cand["content"], str) or not cand["content"].strip():
                errors.append(f"{prefix}.content must be a non-empty string")
            else:
                norm_content = _normalize_lf(cand["content"])
                if len(norm_content.encode("utf-8")) > MAX_CONTENT_BYTES:
                    errors.append(f"{prefix}.content exceeds {MAX_CONTENT_BYTES} bytes")
                _check_safety_patterns(bmode_capture, f"{prefix}.content", norm_content, errors)
                if kind == "references":
                    try:
                        _, body = bmode_assets.parse_frontmatter(norm_content, Path(key or "<reference>"))
                        if not body.strip():
                            errors.append(f"{prefix}.content has empty Markdown body")
                    except ValueError as err:
                        errors.append(f"{prefix}.content invalid frontmatter: {err}")

    return errors


def build_dedupe_context(repo, tracked_map, bmode_dir, bmode_assets):
    """Collect bundled entries, repo .byte-stack entries, and steering lines/tokens."""
    bundled_by_kind = {}
    repo_by_kind = {}
    catalog_entries = []

    for kind in bmode_assets.KINDS:
        bundled_by_kind[kind] = {}
        repo_by_kind[kind] = {}
        b_base = bmode_dir / kind
        if b_base.is_dir():
            for path in sorted(b_base.rglob("*")):
                rel = path.relative_to(b_base)
                if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
                    continue
                if path.is_dir() or (kind in ("playbooks", "workflows") and path.suffix != ".md"):
                    continue
                key = rel.as_posix()
                trigger = bmode_assets.inspect_file(path, kind)
                text = path.read_text(encoding="utf-8", errors="replace") if path.suffix == ".md" else ""
                info = {
                    "origin": "bundled",
                    "kind": kind,
                    "key": key,
                    "trigger": trigger,
                    "title": _extract_h1(text),
                    "tokens": _tokenize(f"{trigger}\n{text}"),
                }
                bundled_by_kind[kind][key] = info
                catalog_entries.append(info)

        r_base = bmode_assets.checked(repo, [".byte-stack", kind])
        if r_base.exists():
            if not r_base.is_dir():
                raise DiagnosticError(f"expected directory: {r_base}")
            for path in sorted(r_base.rglob("*")):
                rel = path.relative_to(r_base)
                if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
                    continue
                bmode_assets.checked(r_base, rel.parts)
                if path.is_dir():
                    continue
                _check_existing_path_is_regular(path)
                key = rel.as_posix()
                try:
                    trigger = bmode_assets.inspect_file(path, kind)
                except ValueError:
                    trigger = ""
                text = path.read_text(encoding="utf-8", errors="replace")
                info = {
                    "origin": "repo",
                    "kind": kind,
                    "key": key,
                    "trigger": trigger,
                    "title": _extract_h1(text) if path.suffix == ".md" else "",
                    "tokens": _tokenize(f"{trigger}\n{text}"),
                    "text": text,
                }
                repo_by_kind[kind][key] = info
                catalog_entries.append(info)

    steering_lines = set()
    steering_sources = []
    for rel_path, mode in sorted(tracked_map.items()):
        if exclusion_reason(rel_path, mode) is not None:
            continue
        if classify_path(rel_path, mode) != "steering":
            continue
        try:
            target = bmode_assets.checked(repo, rel_path.split("/"))
            _check_existing_path_is_regular(target)
            if not target.exists():
                continue
            with target.open("rb") as handle:
                text = handle.read(MAX_PROVENANCE_READ_BYTES).decode("utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if stripped:
                steering_lines.add(stripped)
                unbulleted = _strip_bullet(stripped)
                if unbulleted:
                    steering_lines.add(unbulleted)
        steering_sources.append((rel_path, _tokenize(text)))

    return {
        "bundled": bundled_by_kind,
        "repo": repo_by_kind,
        "catalog_entries": catalog_entries,
        "steering_lines": steering_lines,
        "steering_sources": steering_sources,
    }


def evaluate_dedupe(candidate, existing_text, rendered_text, ctx):
    """Compute explicit dedupe verdict, reason, blocking flags, and soft similar_to warnings."""
    kind = candidate["kind"]
    key = candidate["key"]
    cid = candidate["id"]
    flags = []
    reasons = []

    if existing_text is not None:
        if existing_text == rendered_text:
            flags.append("exists-identical")
            reasons.append(f"existing .byte-stack/{kind}/{key} matches byte-for-byte")
        else:
            flags.append("exists-differs")
            reasons.append(f"existing .byte-stack/{kind}/{key} differs")

    if existing_text is None and key in ctx["bundled"].get(kind, {}):
        flags.append("overrides-bundled")
        reasons.append(
            f"overrides bundled byte-stack {kind}/{key} (pass --override-bundled {cid} to proceed)"
        )

    # Check steering restatement
    prov_paths = [p["path"] for p in candidate["provenance"]]
    all_steering_prov = bool(prov_paths) and all(
        classify_path(p, "100644") == "steering" for p in prov_paths
    )
    cand_lines = _candidate_lines_for_steering(candidate)
    matched_steering = 0
    if cand_lines and ctx["steering_lines"]:
        for line in cand_lines:
            if line in ctx["steering_lines"] or _strip_bullet(line) in ctx["steering_lines"]:
                matched_steering += 1
    steering_ratio = (matched_steering / len(cand_lines)) if cand_lines else 0.0
    if all_steering_prov:
        flags.append("restates-steering")
        reasons.append("all provenance cites standing steering files only")
    elif cand_lines and steering_ratio >= 0.80:
        pct = int(round(steering_ratio * 100))
        flags.append("restates-steering")
        reasons.append(
            f"{matched_steering}/{len(cand_lines)} ({pct}%) of lines occur verbatim in steering files"
        )

    # Check same normalized trigger or H1 title as another catalog entry
    cand_trigger = ""
    cand_title = ""
    if kind in ("playbooks", "workflows"):
        cand_trigger = _normalize_title_or_trigger(candidate["payload"].get("use_when", ""))
        cand_title = _normalize_title_or_trigger(candidate["payload"].get("title", ""))
    elif kind == "references":
        cand_title = _normalize_title_or_trigger(_extract_h1(rendered_text))

    for entry in ctx["catalog_entries"]:
        if entry["kind"] == kind and entry["key"] == key:
            continue
        other_trigger = _normalize_title_or_trigger(entry["trigger"]) if entry["trigger"] else ""
        other_title = _normalize_title_or_trigger(entry["title"]) if entry["title"] else ""
        if (cand_trigger and other_trigger and cand_trigger == other_trigger) or (
            cand_title and other_title and cand_title == other_title
        ):
            flags.append("duplicates-catalog")
            reasons.append(
                f"same trigger or title as {entry['origin']} {entry['kind']}/{entry['key']}"
            )
            break

    # Primary verdict precedence
    for candidate_verdict in (
        "exists-identical",
        "exists-differs",
        "overrides-bundled",
        "restates-steering",
        "duplicates-catalog",
    ):
        if candidate_verdict in flags:
            verdict = candidate_verdict
            break
    else:
        verdict = "new"
        reasons.append("no conflict with bundled catalog, existing .byte-stack/, or steering files")

    # Soft token-overlap warnings
    cand_tokens = _tokenize(_candidate_text_for_tokens(candidate))
    similar = []
    if cand_tokens:
        for entry in ctx["catalog_entries"]:
            if entry["kind"] == kind and entry["key"] == key:
                continue
            other_tokens = entry["tokens"]
            if not other_tokens:
                continue
            shared = len(cand_tokens & other_tokens)
            union = len(cand_tokens | other_tokens)
            min_len = min(len(cand_tokens), len(other_tokens))
            jaccard = shared / union if union else 0.0
            overlap = shared / min_len if min_len else 0.0
            if shared >= 3 and (jaccard >= 0.25 or overlap >= 0.30):
                similar.append(
                    {
                        "score": round(max(jaccard, overlap), 2),
                        "source": f"{entry['origin']}:{entry['kind']}/{entry['key']}",
                    }
                )
        for spath, stokens in ctx["steering_sources"]:
            if not stokens:
                continue
            shared = len(cand_tokens & stokens)
            union = len(cand_tokens | stokens)
            min_len = min(len(cand_tokens), len(stokens))
            jaccard = shared / union if union else 0.0
            overlap = shared / min_len if min_len else 0.0
            if shared >= 3 and (jaccard >= 0.25 or overlap >= 0.30):
                similar.append(
                    {
                        "score": round(max(jaccard, overlap), 2),
                        "source": f"steering:{spath}",
                    }
                )
    similar.sort(key=lambda item: (-item["score"], item["source"]))
    return {
        "dedupe_flags": flags,
        "reason": "; ".join(reasons),
        "similar_to": similar[:5],
        "verdict": verdict,
    }


def apply_atomic_write(repo, parts, kind, content, executable, bmode_assets):
    """Atomically write a references/ or scripts/ file with symlink and mode safety."""
    target = bmode_assets.checked(repo, [".byte-stack", kind, *parts])
    _check_existing_path_is_regular(target)
    existing_mode = stat.S_IMODE(target.lstat().st_mode) if target.exists() else None
    target.parent.mkdir(parents=True, exist_ok=True)
    target = bmode_assets.checked(repo, [".byte-stack", kind, *parts])
    _check_existing_path_is_regular(target)
    fd, tmp_name = tempfile.mkstemp(prefix=".extract-", suffix=".tmp", dir=target.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        umask = os.umask(0)
        os.umask(umask)
        if existing_mode is not None:
            mode = existing_mode
            if kind == "scripts" and executable is True:
                mode = (mode | 0o111) & ~umask
        else:
            base_mode = 0o777 if (kind == "scripts" and executable is True) else 0o666
            mode = base_mode & ~umask
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    bmode_assets.inspect_file(target, kind)
    return target


def _run_capture_subprocess(capture_py, subcmd_args, stdin_text=None):
    return subprocess.run(
        [sys.executable, "-I", str(capture_py), *subcmd_args],
        input=stdin_text,
        capture_output=True,
        text=True,
    )


def _plan_candidate(cand, repo, bmode_assets, bmode_capture, capture_py, dedupe_ctx, update_ids, force_ids, override_ids):
    """Dry-run one candidate, returning (exit_code, plan_dict, error_message)."""
    cid = cand["id"]
    kind = cand["kind"]
    key = cand["key"]
    parts = bmode_assets.validate_key(kind, key)

    try:
        target = bmode_assets.checked(repo, [".byte-stack", kind, *parts])
        _check_existing_path_is_regular(target)
        existing_text = target.read_text(encoding="utf-8") if target.exists() else None
    except (OSError, ValueError) as err:
        return 2, None, str(err)

    target_rel = target.relative_to(repo).as_posix()
    allow_update = cid in update_ids
    allow_force = cid in force_ids
    allow_override = cid in override_ids

    if kind in ("playbooks", "workflows"):
        full_payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "key": key,
            **cand["payload"],
        }
        rendered = bmode_capture.render_playbook(full_payload)
        dedupe = evaluate_dedupe(cand, existing_text, rendered, dedupe_ctx)

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

        status = cap_res["status"]
        diff = cap_res.get("diff", "")
        plan_reason = cap_res.get("reason", "")
        plan_code = proc.returncode
        will_write = status in ("create", "update", "force-overwrite") and plan_code == 0

        # Apply dedupe gates for non-new verdicts (other than exists-identical)
        if plan_code == 0 and status != "unchanged":
            blocking = _blocking_dedupe_reason(cid, dedupe["dedupe_flags"], allow_override, allow_force)
            if blocking is not None:
                status = "conflict"
                plan_code = 3
                will_write = False
                plan_reason = blocking

        return plan_code, {
            "category": cand["category"],
            "dedupe_flags": dedupe["dedupe_flags"],
            "diff": diff,
            "full_payload": full_payload,
            "id": cid,
            "key": key,
            "kind": kind,
            "provenance": cand["provenance"],
            "reason": plan_reason or dedupe["reason"],
            "relative_path": target_rel,
            "similar_to": dedupe["similar_to"],
            "status": status,
            "verdict": dedupe["verdict"],
            "verdict_reason": dedupe["reason"],
            "will_write": will_write,
        }, None

    # references / scripts
    rendered = _normalize_lf(cand["content"])
    dedupe = evaluate_dedupe(cand, existing_text, rendered, dedupe_ctx)
    from_label = "/dev/null" if existing_text is None else f"a/{target_rel}"
    diff = "".join(
        difflib.unified_diff(
            (existing_text or "").splitlines(keepends=True),
            rendered.splitlines(keepends=True),
            fromfile=from_label,
            tofile=f"b/{target_rel}",
        )
    )

    if existing_text is None:
        blocking = _blocking_dedupe_reason(cid, dedupe["dedupe_flags"], allow_override, allow_force)
        if blocking is not None:
            status = "conflict"
            plan_code = 3
            will_write = False
            plan_reason = blocking
        else:
            status = "create"
            plan_code = 0
            will_write = True
            plan_reason = f"new {kind[:-1]}"
    elif existing_text == rendered:
        status = "unchanged"
        plan_code = 0
        will_write = False
        diff = ""
        plan_reason = "already up to date"
    else:
        blocking = _blocking_dedupe_reason(cid, dedupe["dedupe_flags"], allow_override, allow_force)
        if allow_force and blocking is None:
            status = "force-overwrite"
            plan_code = 0
            will_write = True
            plan_reason = f"forced overwrite of existing {target_rel}"
        else:
            status = "conflict"
            plan_code = 3
            will_write = False
            plan_reason = blocking or f"refusing to overwrite differing {target_rel} without --force {cid}"

    return plan_code, {
        "category": cand["category"],
        "dedupe_flags": dedupe["dedupe_flags"],
        "diff": diff,
        "executable": cand.get("executable", False),
        "id": cid,
        "key": key,
        "kind": kind,
        "parts": parts,
        "provenance": cand["provenance"],
        "reason": plan_reason,
        "relative_path": target_rel,
        "rendered": rendered,
        "similar_to": dedupe["similar_to"],
        "status": status,
        "verdict": dedupe["verdict"],
        "verdict_reason": dedupe["reason"],
        "will_write": will_write,
    }, None


def _blocking_dedupe_reason(cid, flags, allow_override, allow_force):
    """Return conflict reason if a dedupe flag lacks its required per-ID opt-in."""
    if "restates-steering" in flags and not allow_force:
        return f"candidate restates steering files; pass --force {cid} to write anyway"
    if "duplicates-catalog" in flags and not allow_force:
        return f"candidate duplicates an existing catalog trigger or title; pass --force {cid} to write anyway"
    if "overrides-bundled" in flags and not (allow_override or allow_force):
        return f"candidate overrides bundled byte-stack asset; pass --override-bundled {cid} or --force {cid}"
    return None


def _public_plan_item(plan, *, written=False, validated=None, resolved_origin=None):
    item = {
        "category": plan["category"],
        "dedupe_flags": plan["dedupe_flags"],
        "diff": plan["diff"],
        "id": plan["id"],
        "key": plan["key"],
        "kind": plan["kind"],
        "provenance": plan["provenance"],
        "reason": plan["reason"],
        "relative_path": plan["relative_path"],
        "similar_to": plan["similar_to"],
        "status": plan["status"],
        "verdict": plan["verdict"],
        "verdict_reason": plan["verdict_reason"],
        "written": written,
    }
    if validated is not None:
        item["validated"] = validated
    if resolved_origin is not None:
        item["resolved_origin"] = resolved_origin
    return item


def cmd_write(args):
    try:
        bmode_dir, bmode_assets, bmode_capture, capture_py = load_bmode(args.bmode)
        repo = bmode_assets.checkout(args.cwd)
        if repo is None:
            raise DiagnosticError("Run extract-assets inside a Git worktree.")
        tracked_map = dict(list_tracked_files(repo))
    except (DiagnosticError, OSError, ValueError) as err:
        print(str(err), file=sys.stderr)
        return 2

    try:
        raw = sys.stdin.read() if args.stdin else args.candidates.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError) as err:
        print(f"invalid candidates JSON: {err}", file=sys.stderr)
        return 1

    errors = validate_candidates_envelope(data, repo, tracked_map, bmode_assets, bmode_capture)

    approve_ids = set(args.approve)
    update_ids = set(args.update)
    force_ids = set(args.force)
    override_ids = set(args.override_bundled)

    if not args.dry_run and not approve_ids:
        errors.append("at least one --approve ID is required unless --dry-run is set")

    candidates = data.get("candidates", []) if isinstance(data, dict) and isinstance(data.get("candidates"), list) else []
    known_ids = {c["id"] for c in candidates if isinstance(c, dict) and isinstance(c.get("id"), str)}
    for flag_name, id_set in (
        ("--approve", approve_ids),
        ("--update", update_ids),
        ("--force", force_ids),
        ("--override-bundled", override_ids),
    ):
        unknown = sorted(id_set - known_ids)
        if unknown:
            errors.append(f"unknown candidate ID(s) in {flag_name}: {', '.join(unknown)}")

    if errors:
        if args.json:
            print(json.dumps({"errors": errors, "status": "invalid"}, indent=2, sort_keys=True))
        else:
            for err in errors:
                print(f"candidate error: {err}", file=sys.stderr)
        return 1

    try:
        dedupe_ctx = build_dedupe_context(repo, tracked_map, bmode_dir, bmode_assets)
    except (DiagnosticError, OSError, ValueError) as err:
        print(_sanitize_text(str(err), repo, bmode_dir, bmode_capture), file=sys.stderr)
        return 2

    selected = [
        cand for cand in candidates
        if (cand["id"] in approve_ids) or (args.dry_run and not approve_ids)
    ]

    # Phase 1: dry-run every selected candidate before writing anything.
    planned = []
    for cand in selected:
        code, plan, err_msg = _plan_candidate(
            cand,
            repo,
            bmode_assets,
            bmode_capture,
            capture_py,
            dedupe_ctx,
            update_ids,
            force_ids,
            override_ids,
        )
        if code in (1, 2):
            sanitized = _sanitize_text(err_msg or "preflight failed", repo, bmode_dir, bmode_capture)
            if args.json and code == 1:
                print(json.dumps({"errors": [sanitized], "status": "invalid"}, indent=2, sort_keys=True))
            else:
                print(sanitized, file=sys.stderr)
            return code
        planned.append((code, plan))

    # Phase 2: dry-run output or per-asset writes.
    results = []
    had_conflict = False

    if args.dry_run:
        for code, plan in planned:
            if code == 3:
                had_conflict = True
            results.append(_public_plan_item(plan, written=False))
    else:
        for code, plan in planned:
            if code == 3:
                had_conflict = True
                results.append(_public_plan_item(plan, written=False))
                continue
            if not plan["will_write"]:
                results.append(_public_plan_item(plan, written=False))
                continue

            cid = plan["id"]
            kind = plan["kind"]
            key = plan["key"]
            if kind in ("playbooks", "workflows"):
                cap_args = ["write", "--stdin", "--json", "--cwd", str(repo)]
                if cid in update_ids:
                    cap_args.append("--update")
                if cid in force_ids:
                    cap_args.append("--force")
                proc = _run_capture_subprocess(
                    capture_py, cap_args, stdin_text=json.dumps(plan["full_payload"])
                )
                if proc.returncode != 0:
                    msg = _sanitize_text(
                        proc.stderr.strip() or proc.stdout.strip(), repo, bmode_dir, bmode_capture
                    )
                    print(msg, file=sys.stderr)
                    return proc.returncode
                written_path = repo / ".byte-stack" / kind / key
                val_proc = _run_capture_subprocess(
                    capture_py, ["validate", str(written_path), "--kind", kind, "--json"]
                )
                if val_proc.returncode != 0:
                    msg = _sanitize_text(
                        val_proc.stderr.strip() or val_proc.stdout.strip(), repo, bmode_dir, bmode_capture
                    )
                    print(f"post-write validation failed for {cid}: {msg}", file=sys.stderr)
                    return val_proc.returncode
                origin, _ = bmode_assets.resolve(repo, kind, key, bmode_dir)
                if origin != "repo":
                    print(f"post-write resolve did not return repo for {cid}", file=sys.stderr)
                    return 2
                results.append(
                    _public_plan_item(plan, written=True, validated=True, resolved_origin=origin)
                )
            else:
                try:
                    apply_atomic_write(
                        repo, plan["parts"], kind, plan["rendered"], plan["executable"], bmode_assets
                    )
                    origin, _ = bmode_assets.resolve(repo, kind, key, bmode_dir)
                    if origin != "repo":
                        raise DiagnosticError(f"post-write resolve did not return repo for {cid}")
                except (DiagnosticError, OSError, ValueError) as err:
                    print(_sanitize_text(str(err), repo, bmode_dir, bmode_capture), file=sys.stderr)
                    return 2
                results.append(_public_plan_item(plan, written=True, resolved_origin=origin))

    exit_code = 3 if had_conflict else 0
    if args.json:
        print(
            json.dumps(
                {
                    "dry_run": args.dry_run,
                    "results": results,
                    "schema_version": SCHEMA_VERSION,
                    "status": "conflict" if had_conflict else "ok",
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        prefix = "dry-run " if args.dry_run else ""
        for item in results:
            print(
                f"{prefix}{item['status']}: {item['relative_path']} "
                f"[verdict={item['verdict']}] ({item['reason']})"
            )
            if item["similar_to"]:
                sims = ", ".join(f"{s['source']} ({s['score']})" for s in item["similar_to"])
                print(f"  similar_to: {sims}")
            if item["diff"]:
                print(item["diff"], end="" if item["diff"].endswith("\n") else "\n")
    return exit_code


def cmd_schema():
    print(SCHEMA_PATH.read_text(encoding="utf-8"), end="")
    return 0


def build_parser():
    top_common = argparse.ArgumentParser(add_help=False)
    top_common.add_argument(
        "--bmode",
        type=Path,
        default=None,
        help="Path to installed bmode skill directory (default: sibling ../bmode)",
    )
    sub_common = argparse.ArgumentParser(add_help=False)
    sub_common.add_argument(
        "--bmode",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to installed bmode skill directory (default: sibling ../bmode)",
    )

    parser = argparse.ArgumentParser(description=__doc__, parents=[top_common])
    sub = parser.add_subparsers(dest="command", required=True)

    inv_p = sub.add_parser(
        "inventory",
        parents=[sub_common],
        help="Scan tracked repository files and .byte-stack/ catalogs (read-only)",
    )
    inv_p.add_argument("--cwd", type=Path, default=Path.cwd(), help="Directory inside target Git worktree")
    inv_p.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES, help="Maximum classified files to read")
    inv_p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="Maximum total bytes to read")

    sub.add_parser("schema", parents=[sub_common], help="Print the extract-candidates JSON Schema")

    wr_p = sub.add_parser(
        "write",
        parents=[sub_common],
        help="Validate, deduplicate, preview, and write approved .byte-stack/ candidates",
    )
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
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "inventory":
        return cmd_inventory(args)
    if args.command == "write":
        return cmd_write(args)
    return cmd_schema()


if __name__ == "__main__":
    sys.exit(main())
