#!/usr/bin/env python3
"""Performance scan CLI for plugins/byte-stack (calibrate, init, run)."""
from __future__ import annotations

import argparse
import inspect
import io
import os
import time
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import traceback
from typing import Any, Callable, Mapping, Sequence

PERF_DIR = Path(__file__).resolve().parent
REPO_ROOT = PERF_DIR.parents[1]
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

import baseline
import scoring

_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA64_RE = re.compile(r"^[0-9a-f]{64}$")


class _CliError(Exception):
    """Fixed-text CLI error; never carries raw user argument values."""


class _HarnessFailure(Exception):
    """Fixed-text harness, host-gate, or environment error (exit 2)."""


class _FixedTextParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - tested via main
        raise _CliError("invalid command arguments")


def _build_parser() -> argparse.ArgumentParser:
    parser = _FixedTextParser(prog="scan.py", add_help=True)
    sub = parser.add_subparsers(dest="command", required=True)

    p_cal = sub.add_parser("calibrate", help="Run A/A calibration scans and write calibration.json")
    p_cal.add_argument("--runs", type=int, default=8, help="Number of A/A calibration runs (default: 8)")
    p_cal.add_argument("--src", type=str, default=None, help="Plugin tree directory override")

    p_init = sub.add_parser("init", help="Run A/B scans and write initial baseline.json")
    p_init.add_argument("--src", type=str, default=None, help="Plugin tree directory override")
    p_init.add_argument(
        "--reset",
        action="store_true",
        help="Replace an existing baseline.json after A/B checks pass",
    )

    p_run = sub.add_parser("run", help="Measure, score, compare against baseline, and optionally update")
    p_run.add_argument("--only", type=str, default=None, help="Comma-separated GROUP or GROUP.METRIC selectors")
    p_run.add_argument("--quick", action="store_true", help="Select every group except SUITE")
    p_run.add_argument("--no-update", action="store_true", help="Never update baseline.json")
    p_run.add_argument("--src", type=str, default=None, help="Plugin tree directory override")
    p_run.add_argument("--dry-score", action="store_true", help="Measure and print sample counts without scoring")
    return parser


def _get_loadavg_1m() -> float:
    return float(os.getloadavg()[0])


def _get_head_commit(repo_root: Path = REPO_ROOT) -> str:
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _HarnessFailure("unable to resolve git HEAD commit") from exc
    sha = res.stdout.strip()
    if _SHA40_RE.fullmatch(sha) is None:
        raise _HarnessFailure("invalid git HEAD commit")
    return sha


def _prepare_src(src_arg: str | None, run_dir: Path, repo_root: Path = REPO_ROOT) -> Path:
    if src_arg is not None:
        src_path = Path(src_arg)
        if not src_path.is_dir():
            raise _HarnessFailure("invalid --src directory")
        return src_path

    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "archive", "HEAD", "plugins/byte-stack"],
            capture_output=True,
            check=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _HarnessFailure("failed to archive plugins/byte-stack from HEAD") from exc

    dest = run_dir / "src_archive"
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(res.stdout), mode="r:") as archive:
            # Python 3.12+ supports filter="data"; keep 3.9+ compatibility.
            extract_kwargs: dict[str, Any] = {}
            if "filter" in inspect.signature(archive.extractall).parameters:
                extract_kwargs["filter"] = "data"
            archive.extractall(dest, **extract_kwargs)
    except (OSError, tarfile.TarError) as exc:
        raise _HarnessFailure("failed to extract archived plugin tree") from exc

    plugin_dir = dest / "plugins" / "byte-stack"
    if not plugin_dir.is_dir():
        raise _HarnessFailure("archived plugin tree missing")
    return plugin_dir


def _is_harness_exception(exc: BaseException) -> bool:
    return type(exc).__name__ == "HarnessError" or isinstance(exc, _HarnessFailure)


def _load_default_seam(
    *,
    measure: Callable[..., Any] | None,
    canaries: Callable[..., Any] | None,
    fingerprint: Callable[..., Any] | None,
    toolchain: Callable[..., Any] | None,
    build_fixtures: Callable[..., Any] | None,
) -> tuple[
    Callable[..., Any],
    Callable[..., Any],
    Callable[..., Any],
    Callable[[Path], Mapping[str, Any]] | None,
    Callable[..., Any],
]:
    if measure is None or canaries is None:
        try:
            import sampler as sampler_mod
        except ImportError as exc:
            raise _HarnessFailure("measurement sampler module unavailable") from exc
        if measure is None:
            measure = sampler_mod.measure
        if canaries is None:
            canaries = sampler_mod.canaries

    if fingerprint is None:
        try:
            import fingerprint as fingerprint_mod
        except ImportError as exc:
            raise _HarnessFailure("fingerprint module unavailable") from exc
        fingerprint = fingerprint_mod.fingerprint

    if build_fixtures is None:
        try:
            import fixtures as fixtures_mod
        except ImportError as exc:
            raise _HarnessFailure("fixtures module unavailable") from exc
        build_fixtures = fixtures_mod.build

    tc_getter: Callable[[Path], Mapping[str, Any]] | None = None
    if toolchain is not None:
        sig = inspect.signature(toolchain)
        positional = [
            p
            for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
        if len(positional) == 0 and not has_varargs:
            tc_getter = lambda _run_dir: toolchain()  # noqa: E731
        else:
            tc_getter = lambda run_dir: toolchain(run_dir)  # noqa: E731

    return measure, canaries, fingerprint, tc_getter, build_fixtures


def _resolve_toolchain(
    tc_getter: Callable[[Path], Mapping[str, Any]] | None,
    run_dir: Path,
) -> Mapping[str, Any]:
    if tc_getter is not None:
        return tc_getter(run_dir)
    try:
        import fingerprint as fingerprint_mod
        import sampler as sampler_mod
    except ImportError as exc:
        raise _HarnessFailure("toolchain modules unavailable") from exc
    ru_bin = sampler_mod.build_ru(run_dir)
    return fingerprint_mod.toolchain(ru_bin)


def _check_loadavg(
    config: Mapping[str, Any],
    loadavg_fn: Callable[[], float],
    sleep_fn: Callable[[float], None] = time.sleep,
) -> float:
    """Wait up to host_gate.load_wait_s for the 1-minute load average to settle at or below the limit.

    A finished scan keeps one core busy, so the load average right after it is near 1.0 and decays over about a minute;
    waiting lets back-to-back scans (calibrate, then init, then run) start on a quiet host instead of exiting 2."""
    limit = float(config["host_gate"]["max_loadavg_1m"])
    wait_s = float(config["host_gate"].get("load_wait_s", 0))
    step = 5.0
    attempts = int(wait_s // step)
    for attempt in range(attempts + 1):
        try:
            current = float(loadavg_fn())
        except OSError as exc:
            raise _HarnessFailure("unable to read host load average") from exc
        if current <= limit:
            return current
        if attempt < attempts:
            sleep_fn(step)
    raise _HarnessFailure("host load average above limit")


def _check_canaries(
    measured: Mapping[str, float],
    calibrated: Mapping[str, float],
    max_rel_diff: float,
) -> None:
    if not isinstance(measured, Mapping):
        raise _HarnessFailure("invalid canary measurement")
    for key, cal_val in calibrated.items():
        if key not in measured:
            raise _HarnessFailure("missing canary measurement")
        cur_val = measured[key]
        if (
            isinstance(cur_val, bool)
            or not isinstance(cur_val, (int, float))
            or cal_val <= 0
            or cur_val <= 0
        ):
            raise _HarnessFailure("invalid canary measurement")
        rel_diff = abs(float(cur_val) - float(cal_val)) / float(cal_val)
        if rel_diff > max_rel_diff:
            raise _HarnessFailure("host canary drift above limit")


def _call_harness(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        if _is_harness_exception(exc):
            raise _HarnessFailure("measurement harness failure") from exc
        raise


def _check_fingerprint_value(fp: Any) -> str:
    if not isinstance(fp, str) or _SHA64_RE.fullmatch(fp) is None:
        raise _HarnessFailure("invalid host fingerprint")
    return fp


def _check_sha64_value(digest: Any, role: str) -> str:
    if not isinstance(digest, str) or _SHA64_RE.fullmatch(digest) is None:
        raise _HarnessFailure(f"invalid {role} digest")
    return digest


def _cat_label(cat: tuple[str, str]) -> str:
    return f"{cat[0]}.{cat[1]}"


def _emit_post_commit(text: str) -> None:
    """Print a summary after a committed state write without altering the exit code."""
    try:
        print(text)
    except Exception:
        pass


def _format_run_summary(report: Mapping[str, Any]) -> str:
    lines: list[str] = []
    exit_code = report["exit_code"]
    verdict = "PASS" if exit_code == 0 else ("REGRESSION" if exit_code == 1 else "ERROR")
    lines.append(f"result: {verdict}")

    if report["partial"]:
        lines.append(
            f"composite: {report['composite']:.2f} (partial, weight {report['composite_weight']:.2f})"
        )
    else:
        lines.append(f"composite: {report['composite']:.2f} (full)")

    lines.append("baseline: updated" if report["baseline_updated"] else "baseline: unchanged")

    raised = report["raised"]
    if raised:
        items = [
            f"{item['category']} ({item['previous']:.2f} -> {item['current']:.2f}, "
            f"pes={item['pes']:.2f}, eps={item['eps']:.2f})"
            for item in raised
        ]
        lines.append("raised: " + ", ".join(items))
    else:
        lines.append("raised: none")

    regressed = report["regressed"]
    if regressed:
        items = []
        for item in regressed:
            if item["error_failed"]:
                items.append(f"{item['category']} (error gate)")
            else:
                items.append(
                    f"{item['category']} (opt={item['opt']:.2f} < "
                    f"mark={item['mark']:.2f} - eps={item['eps']:.2f})"
                )
        lines.append("regressed: " + ", ".join(items))
    else:
        lines.append("regressed: none")

    not_measured = report["not_measured"]
    if not_measured:
        lines.append("not measured: " + ", ".join(not_measured))

    limit_items = []
    for cat_name in report["selected_categories"]:
        info = report["categories"][cat_name]
        lim = info["detection_limit"]
        limit_items.append(f"{cat_name} +{lim['pct']:.1f}% ({lim['points']:.2f} pts)")
    if limit_items:
        lines.append("detection limits: " + ", ".join(limit_items))

    return "\n".join(lines)


def _validate_sample_counts(
    samples: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
    groups: Sequence[str],
) -> None:
    group_set = set(groups)
    for data in samples.values():
        grp = data.get("group")
        if grp not in group_set:
            continue
        expected_n = int(config["groups"][grp]["n"])
        for field in scoring.METRIC_SAMPLE_FIELD.values():
            arr = data.get(field)
            if not isinstance(arr, Sequence) or len(arr) != expected_n:
                raise _HarnessFailure("unexpected sample count")


def _parse_run_selection(args: argparse.Namespace) -> tuple[tuple[str, str], ...]:
    if args.only is not None and args.quick:
        raise _CliError("--only and --quick cannot be combined")
    if args.quick:
        return tuple(cat for cat in scoring.ALL_CATEGORIES if cat[0] != "SUITE")
    if args.only is not None:
        try:
            return scoring.parse_selectors(args.only)
        except ValueError as exc:
            raise _CliError("invalid --only selector") from exc
    return scoring.ALL_CATEGORIES


def _cmd_calibrate(
    args: argparse.Namespace,
    *,
    config: Mapping[str, Any],
    config_sha: str,
    state_dir: Path,
    run_dir: Path,
    measure: Callable[..., Any],
    canaries: Callable[..., Any],
    fingerprint: Callable[..., Any],
    build_fixtures: Callable[..., Any],
    loadavg_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
) -> tuple[int, bool]:
    if args.runs < 2:
        raise _CliError("invalid --runs value")

    _check_loadavg(config, loadavg_fn, sleep_fn)
    host_fp = _check_fingerprint_value(_call_harness(fingerprint))
    fixtures_sha = _check_sha64_value(
        _call_harness(build_fixtures, run_dir / "fixtures"), "fixtures"
    )
    src = _prepare_src(args.src, run_dir)

    rounds = int(config["rounds"])
    warmup = int(config["warmup"])
    runs_data: list[Mapping[str, Mapping[str, Any]]] = []
    canary_series: dict[str, list[float]] = {}

    for idx in range(args.runs):
        can_run = _call_harness(canaries, run_dir / f"cal-{idx}")
        if not isinstance(can_run, Mapping) or not can_run:
            raise _HarnessFailure("invalid canary measurement")
        for key, val in can_run.items():
            if isinstance(val, bool) or not isinstance(val, (int, float)) or val <= 0:
                raise _HarnessFailure("invalid canary measurement")
            canary_series.setdefault(str(key), []).append(float(val))

        samples = _call_harness(
            measure,
            src,
            scoring.GROUPS,
            run_dir / f"cal-{idx}",
            rounds=rounds,
            warmup=warmup,
        )
        _validate_sample_counts(samples, config, scoring.GROUPS)
        runs_data.append(samples)

    calibrated_canaries = {
        key: scoring.quantile(vals, 0.50)
        for key, vals in sorted(canary_series.items())
    }

    try:
        anchors = scoring.compute_anchors(
            runs_data,
            float(config["anchor_multipliers"]["g_p50"]),
            float(config["anchor_multipliers"]["k_p95"]),
        )
        run_scores = [
            scoring.score_samples(samples, anchors, scoring.GROUPS)
            for samples in runs_data
        ]
        eps = scoring.compute_eps(
            run_scores,
            eps_min=float(config["eps"]["min"]),
            iqr_fence=float(config["eps"]["iqr_fence"]),
        )
        violations = scoring.check_calibration_pairs(run_scores, eps)
    except ValueError as exc:
        raise _HarnessFailure("calibration scoring failed") from exc

    report = {
        "command": "calibrate",
        "runs": args.runs,
        "exit_code": 2 if violations else 0,
        "calibration_written": not bool(violations),
        "violations": [
            {
                "category": _cat_label(v.category),
                "run_i": v.run_i,
                "run_j": v.run_j,
                "opt_i": v.opt_i,
                "point_j": v.point_j,
                "eps": v.eps,
            }
            for v in violations
        ],
        "eps": eps,
        "canaries": calibrated_canaries,
    }
    baseline.atomic_write_json(run_dir / "report.json", report)

    if violations:
        print("error: calibration noise fence too tight", file=sys.stderr)
        return 2, False

    cal_record = {
        "schema_version": 1,
        "config_version": int(config["config_version"]),
        "config_sha256": config_sha,
        "fixtures_sha256": fixtures_sha,
        "host_fingerprint": host_fp,
        "calibrated_at": baseline.utc_now_iso(),
        "runs": args.runs,
        "canaries": calibrated_canaries,
        "anchors": anchors,
        "eps": eps,
    }
    eps_vals = [eps[g][m] for g in scoring.GROUPS for m in scoring.METRICS]
    summary = (
        f"result: CALIBRATED (runs={args.runs}, eps min={min(eps_vals):.2f}, max={max(eps_vals):.2f})"
    )
    baseline.save_calibration(state_dir, cal_record)
    _emit_post_commit(summary)
    return 0, True


def _cmd_init(
    args: argparse.Namespace,
    *,
    config: Mapping[str, Any],
    config_sha: str,
    state_dir: Path,
    run_dir: Path,
    measure: Callable[..., Any],
    canaries: Callable[..., Any],
    fingerprint: Callable[..., Any],
    tc_getter: Callable[[Path], Mapping[str, Any]] | None,
    build_fixtures: Callable[..., Any],
    loadavg_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
) -> tuple[int, bool]:
    if not args.reset and os.path.lexists(baseline.baseline_path(state_dir)):
        raise _CliError("baseline already exists; pass --reset to replace it")

    cal, cal_sha = baseline.load_calibration(state_dir)

    _check_loadavg(config, loadavg_fn, sleep_fn)
    host_fp = _check_fingerprint_value(_call_harness(fingerprint))
    if host_fp != cal["host_fingerprint"]:
        raise _HarnessFailure("host fingerprint mismatch")
    if "config_version" in cal and cal["config_version"] != config["config_version"]:
        raise _HarnessFailure("calibration config mismatch")
    if "config_sha256" in cal and cal["config_sha256"] != config_sha:
        raise _HarnessFailure("calibration config mismatch")

    measured_canaries = _call_harness(canaries, run_dir)
    _check_canaries(
        measured_canaries,
        cal["canaries"],
        float(config["host_gate"]["canary_max_rel_diff"]),
    )

    fixtures_sha = _check_sha64_value(
        _call_harness(build_fixtures, run_dir / "fixtures"), "fixtures"
    )
    if "fixtures_sha256" in cal and cal["fixtures_sha256"] != fixtures_sha:
        raise _HarnessFailure("calibration fixtures mismatch")

    tc = _call_harness(_resolve_toolchain, tc_getter, run_dir)
    src = _prepare_src(args.src, run_dir)
    commit = _get_head_commit()

    rounds = int(config["rounds"])
    warmup = int(config["warmup"])
    samples_a = _call_harness(
        measure, src, scoring.GROUPS, run_dir / "init-a", rounds=rounds, warmup=warmup
    )
    _validate_sample_counts(samples_a, config, scoring.GROUPS)
    samples_b = _call_harness(
        measure, src, scoring.GROUPS, run_dir / "init-b", rounds=rounds, warmup=warmup
    )
    _validate_sample_counts(samples_b, config, scoring.GROUPS)

    try:
        scored_a = scoring.score_samples(samples_a, cal["anchors"], scoring.GROUPS)
        scored_b = scoring.score_samples(samples_b, cal["anchors"], scoring.GROUPS)
    except ValueError as exc:
        raise _HarnessFailure("scoring failed") from exc

    group_weights = {g: float(config["groups"][g]["weight"]) for g in scoring.GROUPS}
    metric_weights = {m: float(config["metric_weights"][m]) for m in scoring.METRICS}
    comp_a, _ = scoring.composite_score(
        {cat: cs.point for cat, cs in scored_a.items()}, group_weights, metric_weights
    )
    comp_b, _ = scoring.composite_score(
        {cat: cs.point for cat, cs in scored_b.items()}, group_weights, metric_weights
    )

    marks_a = {g: {m: scored_a[(g, m)].point for m in scoring.METRICS} for g in scoring.GROUPS}
    cmp_ba = scoring.compare_against_baseline(scored_b, marks_a, cal["eps"], scoring.ALL_CATEGORIES)
    a_errors = [cat for cat, cs in scored_a.items() if cs.error_failed]

    if a_errors or cmp_ba.regressed:
        reg_cats = sorted(set(a_errors) | set(cmp_ba.regressed), key=scoring.ALL_CATEGORIES.index)
        report = {
            "command": "init",
            "exit_code": 1,
            "baseline_written": False,
            "composite_a": comp_a,
            "composite_b": comp_b,
            "regressed": [_cat_label(c) for c in reg_cats],
        }
        baseline.atomic_write_json(run_dir / "report.json", report)
        print(
            f"result: INIT_FAILED (composite_a={comp_a:.2f}, composite_b={comp_b:.2f}, "
            f"regressed={', '.join(_cat_label(c) for c in reg_cats)})"
        )
        return 1, False

    chosen_label = "A" if comp_a <= comp_b else "B"
    chosen = scored_a if comp_a <= comp_b else scored_b
    chosen_comp = min(comp_a, comp_b)
    chosen_marks = {
        g: {m: chosen[(g, m)].point for m in scoring.METRICS}
        for g in scoring.GROUPS
    }

    record = baseline.build_baseline_record(
        config=config,
        commit=commit,
        config_sha256=config_sha,
        calibration_sha256=cal_sha,
        fixtures_sha256=fixtures_sha,
        host_fingerprint=host_fp,
        toolchain=tc,
        categories=chosen_marks,
    )
    report = {
        "command": "init",
        "exit_code": 0,
        "baseline_written": True,
        "chosen_run": chosen_label,
        "composite_a": comp_a,
        "composite_b": comp_b,
        "composite": chosen_comp,
    }
    summary = (
        f"result: INITIALIZED (chosen={chosen_label}, composite={chosen_comp:.2f}, "
        f"composite_a={comp_a:.2f}, composite_b={comp_b:.2f})"
    )
    baseline.atomic_write_json(run_dir / "report.json", report)
    # Atomic baseline replace is the commit point.
    baseline.save_baseline(state_dir, record)
    _emit_post_commit(summary)
    return 0, True


def _cmd_run(
    args: argparse.Namespace,
    *,
    selected_categories: tuple[tuple[str, str], ...],
    config: Mapping[str, Any],
    config_sha: str,
    state_dir: Path,
    run_dir: Path,
    measure: Callable[..., Any],
    canaries: Callable[..., Any],
    fingerprint: Callable[..., Any],
    build_fixtures: Callable[..., Any],
    loadavg_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
) -> tuple[int, bool]:
    selected_groups = scoring.groups_for_categories(selected_categories)
    partial = len(selected_categories) != len(scoring.ALL_CATEGORIES)

    if args.dry_score:
        src = _prepare_src(args.src, run_dir)
        samples = _call_harness(
            measure,
            src,
            selected_groups,
            run_dir / "samples",
            rounds=int(config["rounds"]),
            warmup=int(config["warmup"]),
        )
        counts = {name: len(data.get("wall_ms", [])) for name, data in sorted(samples.items())}
        report = {
            "command": "run",
            "dry_score": True,
            "exit_code": 0,
            "sample_counts": counts,
        }
        baseline.atomic_write_json(run_dir / "report.json", report)
        print(f"result: DRY_SCORE (benchmarks={len(counts)})")
        return 0, False

    cal, cal_sha = baseline.load_calibration(state_dir)
    base = baseline.load_baseline(state_dir)

    if base["config_version"] != config["config_version"] or base["config_sha256"] != config_sha:
        raise _HarnessFailure("baseline config mismatch")
    if base["calibration_sha256"] != cal_sha:
        raise _HarnessFailure("baseline calibration mismatch")

    _check_loadavg(config, loadavg_fn, sleep_fn)
    host_fp = _check_fingerprint_value(_call_harness(fingerprint))
    if host_fp != cal["host_fingerprint"] or host_fp != base["host_fingerprint"]:
        raise _HarnessFailure("host fingerprint mismatch")

    measured_canaries = _call_harness(canaries, run_dir)
    _check_canaries(
        measured_canaries,
        cal["canaries"],
        float(config["host_gate"]["canary_max_rel_diff"]),
    )

    fixtures_sha = _check_sha64_value(
        _call_harness(build_fixtures, run_dir / "fixtures"), "fixtures"
    )
    if fixtures_sha != base["fixtures_sha256"]:
        raise _HarnessFailure("baseline fixtures mismatch")
    if "fixtures_sha256" in cal and fixtures_sha != cal["fixtures_sha256"]:
        raise _HarnessFailure("calibration fixtures mismatch")

    src = _prepare_src(args.src, run_dir)
    samples = _call_harness(
        measure,
        src,
        selected_groups,
        run_dir / "samples",
        rounds=int(config["rounds"]),
        warmup=int(config["warmup"]),
    )
    _validate_sample_counts(samples, config, selected_groups)

    try:
        scored = scoring.score_samples(samples, cal["anchors"], selected_groups)
    except ValueError as exc:
        raise _HarnessFailure("scoring failed") from exc

    comparison = scoring.compare_against_baseline(
        scored, base["categories"], cal["eps"], selected_categories
    )

    group_weights = {g: float(config["groups"][g]["weight"]) for g in scoring.GROUPS}
    metric_weights = {m: float(config["metric_weights"][m]) for m in scoring.METRICS}
    comp_value, comp_weight = scoring.composite_score(
        {cat: scored[cat].point for cat in selected_categories},
        group_weights,
        metric_weights,
        selected=selected_categories,
    )

    will_update = comparison.exit_code == 0 and bool(comparison.raised) and not args.no_update
    updated: dict[str, Any] | None = None
    if will_update:
        commit = _get_head_commit()
        updated = baseline.update_baseline_record(
            base,
            config=config,
            scored=scored,
            raised=comparison.raised,
            commit=commit,
        )

    regressed_set = set(comparison.regressed)
    raised_set = set(comparison.raised)
    categories_report: dict[str, Any] = {}
    for cat in scoring.ALL_CATEGORIES:
        label = _cat_label(cat)
        if cat in comparison.not_measured:
            categories_report[label] = {"status": "not measured"}
            continue
        cs = scored[cat]
        lim = comparison.detection_limits[cat]
        status = (
            "regressed"
            if cat in regressed_set
            else ("raised" if cat in raised_set else "passed")
        )
        categories_report[label] = {
            "status": status,
            "point": cs.point,
            "opt": cs.opt,
            "pes": cs.pes,
            "mark": base["categories"][cat[0]][cat[1]],
            "eps": cal["eps"][cat[0]][cat[1]],
            "error_failed": cs.error_failed,
            "worst_benchmark": cs.worst_benchmark,
            "detection_limit": {
                "points": lim.points,
                "factor": lim.factor,
                "pct": lim.pct,
            },
        }

    report = {
        "command": "run",
        "exit_code": comparison.exit_code,
        "partial": partial,
        "selected_categories": [_cat_label(c) for c in selected_categories],
        "composite": comp_value,
        "composite_weight": comp_weight,
        "baseline_updated": will_update,
        "raised": [
            {
                "category": _cat_label(c),
                "previous": base["categories"][c[0]][c[1]],
                "current": scored[c].point,
                "pes": scored[c].pes,
                "eps": cal["eps"][c[0]][c[1]],
            }
            for c in comparison.raised
        ],
        "regressed": [
            {
                "category": _cat_label(c),
                "opt": scored[c].opt,
                "mark": base["categories"][c[0]][c[1]],
                "eps": cal["eps"][c[0]][c[1]],
                "error_failed": scored[c].error_failed,
            }
            for c in comparison.regressed
        ],
        "unchanged": [_cat_label(c) for c in comparison.unchanged],
        "not_measured": [_cat_label(c) for c in comparison.not_measured],
        "categories": categories_report,
    }
    summary = _format_run_summary(report)
    baseline.atomic_write_json(run_dir / "report.json", report)

    committed = False
    if updated is not None:
        # Atomic baseline replace is the commit point.
        baseline.save_baseline(state_dir, updated)
        committed = True

    _emit_post_commit(summary)
    return comparison.exit_code, committed


def main(
    argv: list[str],
    *,
    measure: Callable[..., Any] | None = None,
    canaries: Callable[..., Any] | None = None,
    fingerprint: Callable[..., Any] | None = None,
    toolchain: Callable[..., Any] | None = None,
    build_fixtures: Callable[..., Any] | None = None,
    loadavg: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> int:
    try:
        parser = _build_parser()
        try:
            args = parser.parse_args(argv)
        except SystemExit as exc:
            return 0 if exc.code == 0 else 2
        except _CliError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        loadavg_fn = _get_loadavg_1m if loadavg is None else loadavg
        sleep_fn = time.sleep if sleep is None else sleep
        state_dir = baseline.state_dir_from_env()
        run_dir: Path | None = None
        keep_runs = 3
        committed = False

        try:
            selected_categories: tuple[tuple[str, str], ...] = scoring.ALL_CATEGORIES
            if args.command == "calibrate" and args.runs < 2:
                raise _CliError("invalid --runs value")
            if args.command == "run":
                selected_categories = _parse_run_selection(args)

            with baseline.state_lock(state_dir):
                try:
                    config, config_sha = baseline.load_config()
                    keep_runs = int(config["keep_runs"])
                    if args.command == "init" and not args.reset and os.path.lexists(
                        baseline.baseline_path(state_dir)
                    ):
                        raise _CliError("baseline already exists; pass --reset to replace it")

                    run_dir = baseline.make_run_dir(state_dir)

                    measure_fn, canaries_fn, fp_fn, tc_getter, fixtures_fn = _load_default_seam(
                        measure=measure,
                        canaries=canaries,
                        fingerprint=fingerprint,
                        toolchain=toolchain,
                        build_fixtures=build_fixtures,
                    )

                    if args.command == "calibrate":
                        code, committed = _cmd_calibrate(
                            args,
                            config=config,
                            config_sha=config_sha,
                            state_dir=state_dir,
                            run_dir=run_dir,
                            measure=measure_fn,
                            canaries=canaries_fn,
                            fingerprint=fp_fn,
                            build_fixtures=fixtures_fn,
                            loadavg_fn=loadavg_fn,
                            sleep_fn=sleep_fn,
                        )
                    elif args.command == "init":
                        code, committed = _cmd_init(
                            args,
                            config=config,
                            config_sha=config_sha,
                            state_dir=state_dir,
                            run_dir=run_dir,
                            measure=measure_fn,
                            canaries=canaries_fn,
                            fingerprint=fp_fn,
                            tc_getter=tc_getter,
                            build_fixtures=fixtures_fn,
                            loadavg_fn=loadavg_fn,
                            sleep_fn=sleep_fn,
                        )
                    elif args.command == "run":
                        code, committed = _cmd_run(
                            args,
                            selected_categories=selected_categories,
                            config=config,
                            config_sha=config_sha,
                            state_dir=state_dir,
                            run_dir=run_dir,
                            measure=measure_fn,
                            canaries=canaries_fn,
                            fingerprint=fp_fn,
                            build_fixtures=fixtures_fn,
                            loadavg_fn=loadavg_fn,
                            sleep_fn=sleep_fn,
                        )
                    else:
                        print("error: unknown subcommand", file=sys.stderr)
                        return 2
                    return code
                finally:
                    if run_dir is not None:
                        try:
                            baseline.prune_run_dirs(state_dir, keep=keep_runs)
                        except OSError:
                            pass
                        except Exception:
                            if not committed:
                                raise
        except (_CliError, _HarnessFailure, baseline.StateError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except OSError:
            print("error: filesystem or process error", file=sys.stderr)
            return 2
    except Exception:
        print("error: internal error", file=sys.stderr)
        if os.environ.get("PERF_DEBUG") == "1":
            traceback.print_exc(file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
