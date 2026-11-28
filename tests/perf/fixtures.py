#!/usr/bin/env python3
"""Deterministic fixture builder, runtime materializer, and expected-digest helper."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from benchmarks import BenchmarkSpec, HarnessError, build_specs

EXPECTED_PATH = HERE / "expected.json"

_TIME_RE = re.compile(r"\b\d{2}:\d{2}:\d{2}\b")
_HANDOFF_CHECK_TMP_RE = re.compile(r"handoff-check-[A-Za-z0-9_-]+")
_FIXED_SHA_BASE = "1" * 40
_FIXED_SHA_HEAD = "2" * 40
_GIT_ENV_FIXED = {
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
    "LC_ALL": "C",
}


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _transcript_bytes(target_size: int, *, boundary: bool, model: str = "fixture-model", cache_read: int = 120_000) -> bytes:
    assistant = json.dumps(
        {
            "type": "assistant",
            "isSidechain": False,
            "message": {
                "model": model,
                "content": [{"type": "text", "text": "x" * 1500}],
                "usage": {
                    "input_tokens": 10,
                    "cache_read_input_tokens": cache_read,
                    "cache_creation_input_tokens": 500,
                    "output_tokens": 300,
                },
            },
        },
        separators=(",", ":"),
    )
    user = json.dumps(
        {"type": "user", "message": {"content": "y" * 800}},
        separators=(",", ":"),
    )
    pair = (user + "\n" + assistant + "\n").encode("utf-8")
    repeats = max(1, (target_size + len(pair) - 1) // len(pair))
    chunks = [pair * repeats]
    if boundary:
        # Placed ~2 KB from the end (one assistant line follows).
        b_line = json.dumps(
            {
                "type": "system",
                "subtype": "compact_boundary",
                "timestamp": "2026-01-01T00:00:00Z",
                "compactMetadata": {"trigger": "auto", "preTokens": 300_000},
            },
            separators=(",", ":"),
        )
        chunks.append((b_line + "\n" + assistant + "\n").encode("utf-8"))
    return b"".join(chunks)


def _write_extract_repo(repo: Path) -> None:
    """Create a deterministic 300-file repository covering all extract_assets buckets."""
    files: dict[str, str] = {
        # ci (3)
        ".github/workflows/ci.yml": (
            "name: CI\n"
            "on: [push]\n"
            "jobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - run: pytest -q\n"
        ),
        ".github/workflows/release.yml": (
            "name: Release\n"
            "on: [workflow_dispatch]\n"
            "jobs:\n"
            "  publish:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - run: python3 scripts/release.py --check\n"
        ),
        ".gitlab-ci.yml": (
            "stages:\n"
            "  - verify\n"
            "verify:\n"
            "  script:\n"
            "    - python3 -m unittest\n"
        ),
        # git_hooks (2)
        ".pre-commit-config.yaml": (
            "repos:\n"
            "  - repo: https://example.invalid/hooks\n"
            "    hooks:\n"
            "      - id: lint-check\n"
        ),
        ".husky/pre-commit": "#!/usr/bin/env sh\npython3 -m unittest\n",
        # steering (2)
        "AGENTS.md": (
            "# Repository agent notes\n\n"
            "## Verification\n\n"
            "```sh\n"
            "python3 -m unittest\n"
            "```\n"
        ),
        "CLAUDE.md": (
            "# Notes\n\n"
            "Follow AGENTS.md for test and lint steps.\n"
        ),
        # adrs (4)
        "docs/adr/0001-architecture.md": "# ADR 0001: Architecture\n\nUse pure modules.\n",
        "docs/adr/0002-storage.md": "# ADR 0002: Storage\n\nUse deterministic JSON files.\n",
        "docs/adr/0003-cli.md": "# ADR 0003: CLI\n\nValidate arguments at the boundary.\n",
        "docs/adr/0004-testing.md": "# ADR 0004: Testing\n\nUse stdlib unittest.\n",
        # directives (4)
        "docs/standards.md": "# Standards\n\nKeep error messages fixed text.\n",
        "docs/directives/style.md": "# Style directive\n\nUse explicit imports.\n",
        "CONTRIBUTING.md": (
            "# Contributing\n\n"
            "Run checks before sending a pull request:\n\n"
            "```sh\n"
            "sh scripts/verify.sh\n"
            "```\n"
        ),
        "GLOSSARY.md": "# Glossary\n\n- **Fixture**: deterministic test input.\n",
        # quality (4)
        "ruff.toml": (
            "line-length = 100\n"
            "[lint]\n"
            "select = [\"E\", \"F\", \"W\"]\n"
        ),
        ".editorconfig": "root = true\n\n[*]\nindent_style = space\nindent_size = 4\n",
        "tsconfig.json": json.dumps({"compilerOptions": {"strict": True, "noEmit": True}}, indent=2) + "\n",
        "biome.json": json.dumps({"formatter": {"indentStyle": "space", "lineWidth": 100}}, indent=2) + "\n",
        # task_runners (3)
        "Makefile": (
            ".PHONY: test lint\n"
            "test:\n"
            "\tpython3 -m unittest\n"
            "lint:\n"
            "\truff check .\n"
        ),
        "package.json": json.dumps(
            {
                "name": "fixture-app",
                "version": "1.0.0",
                "scripts": {"build": "tsc --noEmit", "test": "vitest run"},
            },
            indent=2,
        ) + "\n",
        "pyproject.toml": (
            "[project]\n"
            "name = \"fixture-app\"\n"
            "[project.scripts]\n"
            "verify = \"fixture_app:verify\"\n"
        ),
        # scripts (6)
        "scripts/verify.sh": "#!/usr/bin/env sh\n# Run repository verification checks\npython3 -m unittest\n",
        "scripts/build.py": "#!/usr/bin/env python3\n\"\"\"Build package artifacts.\"\"\"\nprint('ok')\n",
        "scripts/lint.sh": "#!/usr/bin/env sh\n# Run linter checks\nruff check .\n",
        "scripts/release.py": "#!/usr/bin/env python3\n\"\"\"Check release tags.\"\"\"\nprint('ok')\n",
        "scripts/check.sh": "#!/usr/bin/env sh\n# Run quick checks\npytest -q\n",
        "scripts/format.py": "#!/usr/bin/env python3\n\"\"\"Format source files.\"\"\"\nprint('ok')\n",
        # excluded (4)
        "vendor/lib/helper.py": "# vendored helper\nVALUE = 1\n",
        "dist/bundle.js": "export const version = 1;\n",
        "notes.local.md": "# Local notes\n",
        "scratch.swp": "swap\n",
    }

    # Fill remaining files up to exactly 300 tracked files.
    idx = 0
    while len(files) < 300:
        pkg = idx // 20
        mod = idx % 20
        if idx % 5 == 0:
            rel = f"docs/guides/guide_{idx:03d}.md"
            body = f"# Guide {idx:03d}\n\nReference notes for component {pkg:02d}/{mod:02d}.\n"
        elif idx % 5 == 1:
            rel = f"tests/test_mod_{idx:03d}.py"
            body = f"\"\"\"Unit test {idx:03d}.\"\"\"\ndef test_case_{idx:03d}():\n    assert {idx} == {idx}\n"
        else:
            rel = f"src/pkg_{pkg:02d}/mod_{mod:02d}.py"
            body = f"\"\"\"Module {pkg:02d}.{mod:02d}.\"\"\"\ndef compute_{idx:03d}(x):\n    return x + {idx}\n"
        files[rel] = body
        idx += 1

    for rel, content in sorted(files.items()):
        _write_text(repo / rel, content)


def _hash_tree(root: Path) -> str:
    h = hashlib.sha256()
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    for p in paths:
        rel = p.relative_to(root).as_posix().encode("utf-8")
        h.update(rel)
        h.update(b"\x00")
        h.update(p.read_bytes())
        h.update(b"\x00")
    return h.hexdigest()


def build(root: Path) -> str:
    """Write every deterministic fixture under root and return 64-hex SHA-256 of generated bytes."""
    root = Path(root)
    if root.exists():
        for child in list(root.iterdir()):
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    root.mkdir(parents=True, exist_ok=True)

    # 1. Synthetic transcripts (64 KB, 1 MB, 4 MB without boundary, 8 MB with boundary ~2 KB from end,
    #    plus a wide-model transcript for PreCompact auto deferral).
    tdir = root / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "t-64k.jsonl").write_bytes(_transcript_bytes(64_000, boundary=False))
    (tdir / "t-1m.jsonl").write_bytes(_transcript_bytes(1_000_000, boundary=False))
    (tdir / "t-4m-noboundary.jsonl").write_bytes(_transcript_bytes(4_000_000, boundary=False))
    (tdir / "t-8m-boundary.jsonl").write_bytes(_transcript_bytes(8_000_000, boundary=True))
    (tdir / "t-defer.jsonl").write_bytes(
        _transcript_bytes(64_000, boundary=False, model="fixture-wide[1m]", cache_read=302_190)
    )

    # 2. Hook project files (no .git here; materialize() initializes git repos).
    proj = root / "proj"
    _write_text(proj / ".gitignore", "handoff/\n")
    _write_text(proj / "app.py", "def main():\n    return 0\n")
    _write_text(
        proj / "handoff" / "handoff-20260101-000000-perffixt.md",
        "# Handoff\n\n- Goal: performance fixture task\n- State: clean worktree\n- Next: continue checks\n",
    )

    # 3. Override project for assets.py resolve.
    proj_ov = root / "proj-override"
    _write_text(proj_ov / "README.md", "# Override fixture repo\n")
    _write_text(
        proj_ov / ".byte-stack" / "playbooks" / "feature.md",
        "# Repo Feature Playbook\n\nUse when: Build a feature in this fixture repository.\n\nRun checks.\n",
    )

    # 4. Hook event JSON templates (using $FX placeholder; zero host paths).
    handoff_rel = "$FX/proj/handoff/handoff-20260101-000000-perffixt.md"
    events: dict[str, dict] = {
        "pre.off.4m.json": {
            "hook_event_name": "PreToolUse",
            "session_id": "perf-fixture",
            "transcript_path": "$FX/transcripts/t-4m-noboundary.jsonl",
            "cwd": "$FX/proj",
            "tool_name": "Read",
            "tool_input": {"file_path": "$FX/proj/app.py"},
        },
        "post.off.64k.json": {
            "hook_event_name": "PostToolUse",
            "session_id": "perf-fixture",
            "transcript_path": "$FX/transcripts/t-64k.jsonl",
            "cwd": "$FX/proj",
            "tool_name": "Read",
            "tool_input": {"file_path": "$FX/proj/app.py"},
        },
        "post.off.1m.json": {
            "hook_event_name": "PostToolUse",
            "session_id": "perf-fixture",
            "transcript_path": "$FX/transcripts/t-1m.jsonl",
            "cwd": "$FX/proj",
            "tool_name": "Read",
            "tool_input": {"file_path": "$FX/proj/app.py"},
        },
        "post.off.4m-noboundary.json": {
            "hook_event_name": "PostToolUse",
            "session_id": "perf-fixture",
            "transcript_path": "$FX/transcripts/t-4m-noboundary.jsonl",
            "cwd": "$FX/proj",
            "tool_name": "Read",
            "tool_input": {"file_path": "$FX/proj/app.py"},
        },
        "post.off.8m-boundary.json": {
            "hook_event_name": "PostToolUse",
            "session_id": "perf-fixture",
            "transcript_path": "$FX/transcripts/t-8m-boundary.jsonl",
            "cwd": "$FX/proj",
            "tool_name": "Read",
            "tool_input": {"file_path": "$FX/proj/app.py"},
        },
        "prompt.off.4m.json": {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "perf-fixture",
            "transcript_path": "$FX/transcripts/t-4m-noboundary.jsonl",
            "cwd": "$FX/proj",
            "prompt": "Continue the fixture task.",
        },
        "pre.pending.4m.allow.json": {
            "hook_event_name": "PreToolUse",
            "session_id": "perf-fixture",
            "transcript_path": "$FX/transcripts/t-4m-noboundary.jsonl",
            "cwd": "$FX/proj",
            "tool_name": "Bash",
            "tool_input": {"command": "git status && mkdir -p handoff"},
        },
        "pre.pending.4m.deny.json": {
            "hook_event_name": "PreToolUse",
            "session_id": "perf-fixture",
            "transcript_path": "$FX/transcripts/t-4m-noboundary.jsonl",
            "cwd": "$FX/proj",
            "tool_name": "Edit",
            "tool_input": {"file_path": "$FX/proj/app.py"},
        },
        "precompact.auto.defer.json": {
            "hook_event_name": "PreCompact",
            "session_id": "perf-fixture",
            "trigger": "auto",
            "transcript_path": "$FX/transcripts/t-defer.jsonl",
            "cwd": "$FX/proj",
        },
        "precompact.auto.done.json": {
            "hook_event_name": "PreCompact",
            "session_id": "perf-fixture",
            "trigger": "auto",
            "transcript_path": "$FX/transcripts/t-defer.jsonl",
            "cwd": "$FX/proj",
        },
        "sessionstart.compact.paste.json": {
            "hook_event_name": "SessionStart",
            "session_id": "perf-fixture",
            "source": "compact",
            "transcript_path": "$FX/transcripts/t-defer.jsonl",
            "cwd": "$FX/proj",
        },
    }
    for name, payload in sorted(events.items()):
        _write_text(root / "events" / name, json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")

    # 5. Saved hook state JSON templates (restored by --prepare before each run).
    #    compacting uses 4102444800 (2100-01-01T00:00:00Z) so time.time() - compacting < 900
    #    without embedding a wall-clock timestamp into the hashed fixture tree.
    states: dict[str, dict] = {
        "pending.json": {
            "status": "pending",
            "since": 1700000000,
            "armed": 1700000000,
            "root": "$FX/proj",
            "at": 132000,
            "path": handoff_rel,
        },
        "done.json": {
            "status": "done",
            "since": 1700000000,
            "armed": 1700000000,
            "root": "$FX/proj",
            "at": 267000,
            "path": handoff_rel,
            "handoff": handoff_rel,
        },
        "compacting.json": {
            "status": "done",
            "since": 1700000000,
            "armed": 1700000000,
            "root": "$FX/proj",
            "at": 267000,
            "path": handoff_rel,
            "handoff": handoff_rel,
            "compacting": 4102444800,
        },
    }
    for name, payload in sorted(states.items()):
        _write_text(root / "states" / name, json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")

    # 6. Briefs fixtures (reviewer values + valid reviewer report).
    reviewer_values = {
        "TASK_ID": "fx-rev-1",
        "REPO_ROOT": "$FX/proj",
        "RUN_DIR": "$FX/out",
        "BASE": _FIXED_SHA_BASE,
        "HEAD": _FIXED_SHA_HEAD,
        "GOAL": "Verify fixture module behavior.",
        "ISSUE": "#1 fixture issue",
        "EXTRA_CONSTRAINTS": "none",
    }
    _write_text(
        root / "briefs" / "reviewer-values.json",
        json.dumps(reviewer_values, indent=2, sort_keys=True) + "\n",
    )
    reviewer_report = (
        "# Review report: fx-rev-1\n\n"
        "**Verdict:** PASS\n\n"
        "The fixture change matches the contract and passes all checks.\n\n"
        "## 1. Fit with the repo\n\n"
        "- **Fit:** Fits cleanly inside the fixture module.\n"
        "- **Rules or principles broken:** none\n\n"
        "## 2. Findings, most urgent first\n\n"
        "No findings.\n\n"
        "## 3. Checks run\n\n"
        "| Check | Command | Exit | Decisive output |\n"
        "| --- | --- | --- | --- |\n"
        "| Unit | `python3 -m unittest` | 0 | OK |\n\n"
        "## 4. Hand-offs\n\n"
        "- none\n\n"
        "## 5. Gaps\n\n"
        "- none\n"
    )
    _write_text(root / "briefs" / "reviewer-report.md", reviewer_report)

    # 7. Capture fixture payload (materialize() runs capture_playbook.py write to produce the validated file).
    capture_payload = {
        "schema_version": 1,
        "kind": "playbooks",
        "key": "perf-fixture.md",
        "title": "Performance fixture playbook",
        "use_when": "Run deterministic verification steps for the fixture repository.",
        "prerequisites": ["Clean git working tree"],
        "steps": [
            "Run python3 -m unittest across the test suite",
            "Confirm exit status is zero before committing",
        ],
        "verification": ["All fixture unit tests exit 0"],
        "guardrails": ["Do not modify bundled plugin files"],
    }
    _write_text(
        root / "capture" / "payload.json",
        json.dumps(capture_payload, indent=2, sort_keys=True) + "\n",
    )

    # 8. Extract fixture: 300-file repo + valid candidates.json.
    _write_extract_repo(root / "extract-repo")
    candidates = {
        "schema_version": 1,
        "candidates": [
            {
                "id": "playbooks/release-notes.md",
                "category": "workflow",
                "kind": "playbooks",
                "key": "release-notes.md",
                "provenance": [{"path": "Makefile", "command": "python3 -m unittest", "line": 3}],
                "rationale": "Captures the Makefile unit test workflow.",
                "payload": {
                    "title": "Release notes",
                    "use_when": "Prepare release notes for a tagged version.",
                    "steps": [
                        "Run python3 -m unittest across the suite",
                        "Verify release tags before publishing",
                    ],
                    "verification": ["Confirm all unit tests exit 0"],
                },
            },
            {
                "id": "workflows/ci-preflight.md",
                "category": "workflow",
                "kind": "workflows",
                "key": "ci-preflight.md",
                "provenance": [{"path": ".github/workflows/ci.yml", "command": "pytest -q"}],
                "rationale": "Mirrors the CI test step locally.",
                "payload": {
                    "title": "CI preflight",
                    "steps": ["Run pytest -q before pushing changes"],
                    "verification": ["All CI checks pass with exit 0"],
                },
            },
            {
                "id": "references/python-style.md",
                "category": "convention",
                "kind": "references",
                "key": "python-style.md",
                "provenance": [{"path": "ruff.toml", "key": "lint.select"}],
                "rationale": "Summarizes repository Ruff configuration.",
                "content": "# Python style\n\nFollow Ruff E, F, and W rules with a 100-char limit.\n",
            },
            {
                "id": "scripts/run-checks.sh",
                "category": "knowledge",
                "kind": "scripts",
                "key": "run-checks.sh",
                "provenance": [{"path": "scripts/verify.sh", "command": "python3 -m unittest"}],
                "rationale": "Wraps the verification script.",
                "content": "#!/usr/bin/env sh\nset -eu\npython3 -m unittest\n",
                "executable": True,
            },
        ],
    }
    _write_text(
        root / "extract" / "candidates.json",
        json.dumps(candidates, indent=2, sort_keys=True) + "\n",
    )

    return _hash_tree(root)


def _git_init_repo(repo: Path, git_home: Path, *, stage_all: bool = False) -> None:
    env = {**os.environ, "HOME": str(git_home), **_GIT_ENV_FIXED}
    repo.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "init", "-q", str(repo)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise HarnessError("failed to initialize fixture git repository")
    if stage_all:
        proc = subprocess.run(
            ["git", "-C", str(repo), "add", "-A"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            raise HarnessError("failed to stage fixture git repository")


def _expand_templates(src_dir: Path, dst_dir: Path, work_str: str) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for src_file in sorted(src_dir.glob("*.json")):
        text = src_file.read_text(encoding="utf-8").replace("$FX", work_str)
        (dst_dir / src_file.name).write_text(text, encoding="utf-8")


def materialize(fx_root: Path, work_dir: Path, src: Path) -> None:
    """Create runnable git repos, expanded event/state JSONs, and captured playbook under work_dir."""
    fx_root = Path(fx_root).resolve()
    work_dir = Path(work_dir).resolve()
    src = Path(src).resolve()
    if not fx_root.is_dir():
        raise HarnessError("fixture root does not exist")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    shutil.copytree(fx_root, work_dir)

    git_home = work_dir / "git-home"
    git_home.mkdir(parents=True, exist_ok=True)
    (work_dir / "hook-home" / ".claude" / "handoff-state").mkdir(parents=True, exist_ok=True)
    (work_dir / "out").mkdir(parents=True, exist_ok=True)
    (work_dir / "tmp").mkdir(parents=True, exist_ok=True)

    _git_init_repo(work_dir / "proj", git_home)
    _git_init_repo(work_dir / "proj-override", git_home)
    _git_init_repo(work_dir / "extract-repo", git_home, stage_all=True)
    _git_init_repo(work_dir / "capture-repo", git_home)
    _git_init_repo(work_dir / "init-repo", git_home)

    # Generate the capture validate fixture via capture_playbook.py write (required: bundled playbooks fail validate).
    capture_py = src / "skills" / "bmode" / "scripts" / "capture_playbook.py"
    if not capture_py.is_file():
        raise HarnessError("capture_playbook.py is missing in target source")
    proc = subprocess.run(
        [
            sys.executable,
            str(capture_py),
            "write",
            "--payload",
            str(work_dir / "capture" / "payload.json"),
            "--cwd",
            str(work_dir / "capture-repo"),
        ],
        cwd=str(work_dir / "capture-repo"),
        env={**os.environ, "HOME": str(git_home), "LC_ALL": "C"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise HarnessError("failed to generate capture validate fixture")

    work_str = str(work_dir)
    _expand_templates(work_dir / "events", work_dir / "runtime" / "events", work_str)
    _expand_templates(work_dir / "states", work_dir / "runtime" / "states", work_str)
    values_text = (work_dir / "briefs" / "reviewer-values.json").read_text(encoding="utf-8")
    (work_dir / "runtime" / "reviewer-values.json").write_text(
        values_text.replace("$FX", work_str),
        encoding="utf-8",
    )


def normalize_output(stdout: str, fx_root: Path, src: Path | None = None) -> str:
    """Normalize fixture root to $FX, target src to $SRC, temp check dir, and HH:MM:SS to 00:00:00."""
    text = stdout
    replacements: list[tuple[str, str]] = []
    if src is not None:
        for candidate in (str(src.resolve()), str(src)):
            if candidate:
                replacements.append((candidate, "$SRC"))
    for candidate in (str(fx_root.resolve()), str(fx_root)):
        if candidate:
            replacements.append((candidate, "$FX"))
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    for raw, token in replacements:
        text = text.replace(raw, token)
    text = _HANDOFF_CHECK_TMP_RE.sub("handoff-check-$TMP", text)
    text = _TIME_RE.sub("00:00:00", text)
    return text


def digest_output(stdout: str, fx_root: Path, src: Path | None = None) -> str:
    """Return 64-hex SHA-256 of normalized stdout."""
    norm = normalize_output(stdout, fx_root, src)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def run_spec_once(spec: BenchmarkSpec, work_dir: Path, src: Path) -> tuple[int, str]:
    """Run one benchmark untimed (including its prepare step) and return (exit_code, stdout_sha256)."""
    if spec.prepare_argv:
        prep = subprocess.run(
            list(spec.prepare_argv),
            cwd=str(spec.cwd),
            env=dict(spec.env),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if prep.returncode != 0:
            raise HarnessError("benchmark prepare command failed")
    stdin_bytes = spec.stdin_file.read_bytes() if spec.stdin_file else b""
    proc = subprocess.run(
        list(spec.argv),
        cwd=str(spec.cwd),
        env=dict(spec.env),
        input=stdin_bytes,
        capture_output=True,
        timeout=120,
    )
    stdout = proc.stdout.decode("utf-8", errors="replace")
    return proc.returncode, digest_output(stdout, work_dir, src)


def unpack_head_archive(dest: Path) -> Path:
    """Unpack `git archive HEAD plugins/byte-stack` into dest and return the plugin directory."""
    repo_root = HERE.parents[1]
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "archive", "HEAD", "plugins/byte-stack"],
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise HarnessError("failed to archive HEAD plugins/byte-stack")
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tf:
        tf.extractall(dest, filter="data") if sys.version_info >= (3, 12) else tf.extractall(dest)
    plugin_dir = dest / "plugins" / "byte-stack"
    if not plugin_dir.is_dir():
        raise HarnessError("archived plugin tree is missing")
    return plugin_dir


def generate_expected(src: Path) -> dict[str, dict[str, object]]:
    """Run every benchmark once against src and return the expected exit-code and digest map."""
    with tempfile.TemporaryDirectory(prefix="perf-expected-") as tmp:
        tmp_path = Path(tmp)
        fx_dir = tmp_path / "fx"
        work_dir = tmp_path / "work"
        build(fx_dir)
        materialize(fx_dir, work_dir, src)
        specs = build_specs(src, work_dir)
        out: dict[str, dict[str, object]] = {}
        for spec in specs:
            rc, sha = run_spec_once(spec, work_dir, src)
            out[spec.name] = {
                "group": spec.group,
                "exit_code": rc,
                "stdout_sha256": sha,
            }
        return out


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(f"{self.prog}: error: invalid or missing arguments (run with --help)", file=sys.stderr)
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description="Build deterministic byte-stack perf fixtures or regenerate expected.json.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path, help="Write deterministic fixtures into DIR and print SHA-256")
    mode.add_argument(
        "--write-expected",
        action="store_true",
        help="Regenerate expected.json from --src (or git archive HEAD plugins/byte-stack)",
    )
    mode.add_argument(
        "--check-expected",
        action="store_true",
        help="Verify every benchmark against expected.json",
    )
    parser.add_argument("--src", type=Path, default=None, help="Path to unpacked plugins/byte-stack tree")
    parser.add_argument("--expected", type=Path, default=EXPECTED_PATH, help="Path to expected.json")
    args = parser.parse_args(argv)

    try:
        if args.out is not None:
            digest = build(args.out)
            print(digest)
            return 0

        with tempfile.TemporaryDirectory(prefix="perf-src-") as tmp_src:
            src_dir = args.src.resolve() if args.src is not None else unpack_head_archive(Path(tmp_src))
            actual = generate_expected(src_dir)

        if args.write_expected:
            args.expected.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"wrote {len(actual)} benchmark expectations")
            return 0

        if not args.expected.is_file():
            raise HarnessError("expected digest table is missing or invalid")
        expected = json.loads(args.expected.read_text(encoding="utf-8"))
        mismatches = [
            name for name, exp in expected.items() if actual.get(name) != exp
        ] + [name for name in actual if name not in expected]
        if mismatches:
            print(f"digest mismatch count: {len(mismatches)}", file=sys.stderr)
            return 1
        print(f"verified {len(actual)} benchmark expectations")
        return 0
    except (HarnessError, OSError, ValueError) as exc:
        msg = str(exc) if isinstance(exc, HarnessError) else "fixture operation failed"
        print(msg, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
