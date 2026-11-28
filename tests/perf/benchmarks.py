"""Benchmark registry, groups, metrics, and runtime command specs for byte-stack perf scan."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import sys
from typing import Mapping, Sequence

GROUPS: tuple[str, ...] = (
    "HOOK_HOT",
    "HOOK_LIFECYCLE",
    "ASSETS",
    "BRIEFS",
    "CAPTURE",
    "EXTRACT",
    "INIT",
    "SUITE",
)

METRICS: tuple[str, ...] = ("L", "U", "M", "IO")

SAMPLE_COUNTS: dict[str, int] = {
    "HOOK_HOT": 200,
    "HOOK_LIFECYCLE": 200,
    "ASSETS": 200,
    "BRIEFS": 200,
    "CAPTURE": 200,
    "EXTRACT": 200,
    "INIT": 200,
    "SUITE": 100,
}

_HOOK_STRIP_ENV = frozenset({
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE",
    "CLAUDE_CODE_DISABLE_1M_CONTEXT",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
    "CLAUDE_PROJECT_DIR",
})


class HarnessError(Exception):
    """Any harness, tool, or fixture failure. Message is fixed text naming the failing role."""


@dataclass(frozen=True)
class BenchmarkSpec:
    name: str
    group: str
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]
    stdin_file: Path | None = None
    prepare_argv: tuple[str, ...] | None = None

    @property
    def prepare_cmd(self) -> str | None:
        return shlex.join(self.prepare_argv) if self.prepare_argv else None


def _base_env(work_dir: Path, *, home: Path | None = None) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("HANDOFF_") and k not in _HOOK_STRIP_ENV
    }
    env["HOME"] = str(home if home is not None else work_dir / "git-home")
    env["TMPDIR"] = str(work_dir / "tmp")
    env["LC_ALL"] = "C"
    return env


def build_specs(
    src: Path,
    work_dir: Path,
    selected_groups: Sequence[str] | None = None,
) -> list[BenchmarkSpec]:
    """Build ordered benchmark command specifications against an unpacked src and materialized work_dir."""
    groups = tuple(GROUPS if selected_groups is None else selected_groups)
    for g in groups:
        if g not in SAMPLE_COUNTS:
            raise HarnessError("unknown benchmark group")
    wanted = set(groups)

    py = sys.executable
    src = src.resolve()
    work_dir = work_dir.resolve()

    hook_py = str(src / "hooks" / "handoff-guard.py")
    check_hook_py = str(src / "hooks" / "check-handoff-guard.py")
    assets_py = str(src / "skills" / "bmode" / "scripts" / "assets.py")
    fill_brief_py = str(src / "skills" / "bmode" / "references" / "briefs" / "fill-brief.py")
    check_report_py = str(src / "skills" / "bmode" / "references" / "briefs" / "check-report.py")
    capture_py = str(src / "skills" / "bmode" / "scripts" / "capture_playbook.py")
    extract_py = str(src / "skills" / "extract-assets" / "scripts" / "extract_assets.py")
    init_py = str(src / "skills" / "init" / "scripts" / "init.py")

    proj = work_dir / "proj"
    proj_override = work_dir / "proj-override"
    extract_repo = work_dir / "extract-repo"
    capture_repo = work_dir / "capture-repo"
    init_repo = work_dir / "init-repo"
    hook_home = work_dir / "hook-home"
    state_target = hook_home / ".claude" / "handoff-state" / "perf-fixture.json"
    rt_events = work_dir / "runtime" / "events"
    rt_states = work_dir / "runtime" / "states"
    rt_values = work_dir / "runtime" / "reviewer-values.json"

    hook_env = _base_env(work_dir, home=hook_home)
    hook_env["CLAUDE_PROJECT_DIR"] = str(proj)
    hook_noop_env = {**hook_env, "HANDOFF_AT": "0"}
    cli_env = _base_env(work_dir)

    rm_state = ("rm", "-f", str(state_target))
    cp_pending = ("cp", "-f", str(rt_states / "pending.json"), str(state_target))
    cp_done = ("cp", "-f", str(rt_states / "done.json"), str(state_target))
    cp_compacting = ("cp", "-f", str(rt_states / "compacting.json"), str(state_target))
    fresh_init = (
        "/bin/sh",
        "-c",
        'find "$1" -mindepth 1 -maxdepth 1 -exec rm -rf {} + && git init -q "$1"',
        "_",
        str(init_repo),
    )

    all_specs: list[BenchmarkSpec] = [
        # HOOK_HOT
        BenchmarkSpec(
            name="hook.pre.off.4m",
            group="HOOK_HOT",
            argv=(py, hook_py),
            cwd=proj,
            env=hook_env,
            stdin_file=rt_events / "pre.off.4m.json",
            prepare_argv=rm_state,
        ),
        BenchmarkSpec(
            name="hook.post.off.64k",
            group="HOOK_HOT",
            argv=(py, hook_py),
            cwd=proj,
            env=hook_env,
            stdin_file=rt_events / "post.off.64k.json",
            prepare_argv=rm_state,
        ),
        BenchmarkSpec(
            name="hook.post.off.1m",
            group="HOOK_HOT",
            argv=(py, hook_py),
            cwd=proj,
            env=hook_env,
            stdin_file=rt_events / "post.off.1m.json",
            prepare_argv=rm_state,
        ),
        BenchmarkSpec(
            name="hook.post.off.4m-noboundary",
            group="HOOK_HOT",
            argv=(py, hook_py),
            cwd=proj,
            env=hook_env,
            stdin_file=rt_events / "post.off.4m-noboundary.json",
            prepare_argv=rm_state,
        ),
        BenchmarkSpec(
            name="hook.post.off.8m-boundary",
            group="HOOK_HOT",
            argv=(py, hook_py),
            cwd=proj,
            env=hook_env,
            stdin_file=rt_events / "post.off.8m-boundary.json",
            prepare_argv=rm_state,
        ),
        BenchmarkSpec(
            name="hook.prompt.off.4m",
            group="HOOK_HOT",
            argv=(py, hook_py),
            cwd=proj,
            env=hook_env,
            stdin_file=rt_events / "prompt.off.4m.json",
            prepare_argv=rm_state,
        ),
        BenchmarkSpec(
            name="hook.pre.pending.4m.allow",
            group="HOOK_HOT",
            argv=(py, hook_py),
            cwd=proj,
            env=hook_env,
            stdin_file=rt_events / "pre.pending.4m.allow.json",
            prepare_argv=cp_pending,
        ),
        BenchmarkSpec(
            name="hook.pre.pending.4m.deny",
            group="HOOK_HOT",
            argv=(py, hook_py),
            cwd=proj,
            env=hook_env,
            stdin_file=rt_events / "pre.pending.4m.deny.json",
            prepare_argv=cp_pending,
        ),
        BenchmarkSpec(
            name="hook.noop.handoff0",
            group="HOOK_HOT",
            argv=(py, hook_py),
            cwd=proj,
            env=hook_noop_env,
            stdin_file=rt_events / "pre.off.4m.json",
            prepare_argv=rm_state,
        ),
        # HOOK_LIFECYCLE
        BenchmarkSpec(
            name="hook.precompact.auto.defer",
            group="HOOK_LIFECYCLE",
            argv=(py, hook_py),
            cwd=proj,
            env=hook_env,
            stdin_file=rt_events / "precompact.auto.defer.json",
            prepare_argv=rm_state,
        ),
        BenchmarkSpec(
            name="hook.precompact.auto.done",
            group="HOOK_LIFECYCLE",
            argv=(py, hook_py),
            cwd=proj,
            env=hook_env,
            stdin_file=rt_events / "precompact.auto.done.json",
            prepare_argv=cp_done,
        ),
        BenchmarkSpec(
            name="hook.sessionstart.compact.paste",
            group="HOOK_LIFECYCLE",
            argv=(py, hook_py),
            cwd=proj,
            env=hook_env,
            stdin_file=rt_events / "sessionstart.compact.paste.json",
            prepare_argv=cp_compacting,
        ),
        # ASSETS
        BenchmarkSpec(
            name="assets.list-playbooks",
            group="ASSETS",
            argv=(py, assets_py, "--cwd", str(proj), "list-playbooks"),
            cwd=proj,
            env=cli_env,
        ),
        BenchmarkSpec(
            name="assets.list-references",
            group="ASSETS",
            argv=(py, assets_py, "--cwd", str(proj), "list", "references"),
            cwd=proj,
            env=cli_env,
        ),
        BenchmarkSpec(
            name="assets.resolve-bundled",
            group="ASSETS",
            argv=(py, assets_py, "--cwd", str(proj), "resolve", "playbooks", "feature.md"),
            cwd=proj,
            env=cli_env,
        ),
        BenchmarkSpec(
            name="assets.resolve-override",
            group="ASSETS",
            argv=(py, assets_py, "--cwd", str(proj_override), "resolve", "playbooks", "feature.md"),
            cwd=proj_override,
            env=cli_env,
        ),
        # BRIEFS
        BenchmarkSpec(
            name="briefs.fill-reviewer",
            group="BRIEFS",
            argv=(
                py,
                fill_brief_py,
                "reviewer",
                "--values",
                str(rt_values),
                "--out",
                str(work_dir / "out" / "reviewer-brief.md"),
            ),
            cwd=proj,
            env=cli_env,
            prepare_argv=("rm", "-f", str(work_dir / "out" / "reviewer-brief.md")),
        ),
        BenchmarkSpec(
            name="briefs.fill-keys-implementor",
            group="BRIEFS",
            argv=(py, fill_brief_py, "--keys", "implementor"),
            cwd=proj,
            env=cli_env,
        ),
        BenchmarkSpec(
            name="briefs.check-report-reviewer",
            group="BRIEFS",
            argv=(py, check_report_py, "reviewer", str(work_dir / "briefs" / "reviewer-report.md")),
            cwd=proj,
            env=cli_env,
        ),
        # CAPTURE
        BenchmarkSpec(
            name="capture.schema",
            group="CAPTURE",
            argv=(py, capture_py, "schema"),
            cwd=proj,
            env=cli_env,
        ),
        BenchmarkSpec(
            name="capture.validate",
            group="CAPTURE",
            argv=(
                py,
                capture_py,
                "validate",
                str(capture_repo / ".byte-stack" / "playbooks" / "perf-fixture.md"),
                "--json",
            ),
            cwd=capture_repo,
            env=cli_env,
        ),
        BenchmarkSpec(
            name="capture.write-dry-run",
            group="CAPTURE",
            argv=(
                py,
                capture_py,
                "write",
                "--dry-run",
                "--payload",
                str(work_dir / "capture" / "payload.json"),
                "--cwd",
                str(proj),
            ),
            cwd=proj,
            env=cli_env,
        ),
        # EXTRACT
        BenchmarkSpec(
            name="extract.inventory",
            group="EXTRACT",
            argv=(py, extract_py, "inventory", "--cwd", str(extract_repo)),
            cwd=extract_repo,
            env=cli_env,
        ),
        BenchmarkSpec(
            name="extract.write-dry-run",
            group="EXTRACT",
            argv=(
                py,
                extract_py,
                "write",
                "--dry-run",
                "--candidates",
                str(work_dir / "extract" / "candidates.json"),
                "--cwd",
                str(extract_repo),
            ),
            cwd=extract_repo,
            env=cli_env,
        ),
        # INIT
        BenchmarkSpec(
            name="init.fresh-repo",
            group="INIT",
            argv=(py, init_py),
            cwd=init_repo,
            env=cli_env,
            prepare_argv=fresh_init,
        ),
        # SUITE
        BenchmarkSpec(
            name="suite.check-handoff-guard",
            group="SUITE",
            argv=(py, check_hook_py, hook_py),
            cwd=proj,
            env=cli_env,
        ),
    ]

    return [spec for spec in all_specs if spec.group in wanted]
