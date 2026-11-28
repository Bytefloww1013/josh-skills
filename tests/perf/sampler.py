"""Hyperfine + ru sampling driver for byte-stack performance scan."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import statistics
import subprocess
import sys
from typing import Mapping, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from benchmarks import BenchmarkSpec, GROUPS, HarnessError, SAMPLE_COUNTS, build_specs
import fixtures

_RU_SOURCE = HERE / "ru.c"
_EXPECTED_PATH = HERE / "expected.json"
_CANARY_RUNS = 30
_CANARY_WARMUP = 3
_PIN_CPU = 0


def build_ru(out_dir: Path) -> Path:
    """Compile ru.c with cc -O2 into out_dir/ru, or validate the RU env override."""
    override = os.environ.get("RU")
    if override is not None:
        candidate = Path(override)
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise HarnessError("ru binary override is missing or not executable")
        return candidate

    cc = shutil.which("cc")
    if not cc:
        raise HarnessError("C compiler is unavailable")
    if not _RU_SOURCE.is_file():
        raise HarnessError("ru source file is missing")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    binary = out_dir / "ru"
    try:
        proc = subprocess.run(
            [cc, "-O2", "-Wall", "-Wextra", "-o", str(binary), str(_RU_SOURCE)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HarnessError("failed to compile ru helper") from exc
    if proc.returncode != 0 or not binary.is_file() or not os.access(binary, os.X_OK):
        raise HarnessError("failed to compile ru helper")
    return binary


def _require_hyperfine() -> str:
    exe = shutil.which("hyperfine")
    if not exe:
        raise HarnessError("hyperfine is unavailable")
    return exe


def _require_ru_executable(ru: Path) -> None:
    if not ru.is_file() or not os.access(ru, os.X_OK):
        raise HarnessError("ru helper binary is missing or not executable")


def _taskset_prefix() -> list[str]:
    ts = shutil.which("taskset")
    if not ts:
        return []
    try:
        probe = subprocess.run([ts, "-c", str(_PIN_CPU), "true"], capture_output=True, timeout=5)
        if probe.returncode == 0:
            return [ts, "-c", str(_PIN_CPU)]
    except (OSError, subprocess.SubprocessError):
        pass
    return []


def _parse_ru_lines(ru_out: Path, expected_total: int) -> list[tuple[int, int, int, int, int, int, int]]:
    try:
        lines = [line for line in ru_out.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        raise HarnessError("ru output file is unreadable") from exc
    if len(lines) != expected_total:
        raise HarnessError("ru output line count mismatch")
    parsed: list[tuple[int, int, int, int, int, int, int]] = []
    for line in lines:
        parts = line.split()
        if len(parts) != 7:
            raise HarnessError("malformed ru output line")
        try:
            vals = tuple(int(p) for p in parts)
        except ValueError as exc:
            raise HarnessError("malformed ru output line") from exc
        parsed.append(vals)  # type: ignore[arg-type]
    return parsed


def _run_hyperfine_round(
    hyperfine_exe: str,
    pin_prefix: list[str],
    ru: Path,
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    runs: int,
    warmup: int,
    json_out: Path,
    ru_out: Path,
    stdin_file: Path | None = None,
    prepare_cmd: str | None = None,
) -> tuple[list[float], list[tuple[int, int, int, int, int, int, int]]]:
    _require_ru_executable(ru)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    ru_out.parent.mkdir(parents=True, exist_ok=True)

    cmd_str = shlex.join([str(ru), *argv])
    hf_cmd: list[str] = [
        *pin_prefix,
        hyperfine_exe,
        "-N",
        "-i",
        "--warmup",
        str(warmup),
        "--runs",
        str(runs),
        "--export-json",
        str(json_out),
    ]
    if stdin_file is not None:
        hf_cmd.extend(["--input", str(stdin_file)])
    if prepare_cmd is not None:
        hf_cmd.extend(["--prepare", prepare_cmd])
    hf_cmd.append(cmd_str)

    # `sh` opens the ru output on fd 3 (append) and then execs hyperfine, so every measured command inherits it. This avoids a
    # preexec_fn dup2, which Python 3.9 undoes when it closes fds not listed in pass_fds.
    ru_out.write_bytes(b"")
    os.chmod(ru_out, 0o600)
    try:
        proc = subprocess.run(
            ["sh", "-c", 'exec "$@" 3>>"$PERF_RU_OUT"', "sh", *hf_cmd],
            cwd=str(cwd),
            env={**dict(env), "PERF_RU_OUT": str(ru_out)},
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HarnessError("hyperfine invocation failed") from exc

    if proc.returncode != 0:
        raise HarnessError("hyperfine exited non-zero")

    try:
        payload = json.loads(json_out.read_text(encoding="utf-8"))
        times_s = payload["results"][0]["times"]
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise HarnessError("hyperfine output is missing or invalid") from exc

    if not isinstance(times_s, list) or len(times_s) != runs:
        raise HarnessError("hyperfine sample count mismatch")

    ru_rows = _parse_ru_lines(ru_out, warmup + runs)
    measured_rows = ru_rows[warmup:]
    if len(measured_rows) != len(times_s):
        raise HarnessError("ru output line count mismatch")

    wall_ms = [float(t) * 1000.0 for t in times_s]
    return wall_ms, measured_rows


def _load_expected() -> dict[str, dict[str, object]]:
    try:
        data = json.loads(_EXPECTED_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HarnessError("expected digest table is missing or invalid") from exc
    if not isinstance(data, dict):
        raise HarnessError("expected digest table is missing or invalid")
    return data


def _check_digests(
    specs: Sequence[BenchmarkSpec],
    expected: Mapping[str, Mapping[str, object]],
    work_dir: Path,
    src: Path,
) -> dict[str, bool]:
    ok: dict[str, bool] = {}
    for spec in specs:
        exp = expected.get(spec.name)
        if not isinstance(exp, Mapping):
            raise HarnessError("benchmark missing from expected digest table")
        rc, sha = fixtures.run_spec_once(spec, work_dir, src)
        ok[spec.name] = (rc == exp.get("exit_code") and sha == exp.get("stdout_sha256"))
    return ok


def measure(
    src: Path,
    selected_groups: Sequence[str],
    run_dir: Path,
    *,
    rounds: int = 4,
    warmup: int = 3,
    _sample_counts: Mapping[str, int] | None = None,
) -> dict[str, dict]:
    """Measure all benchmarks in selected_groups against src and return contract sample dicts."""
    src = Path(src).resolve()
    run_dir = Path(run_dir).resolve()
    if not (src / "hooks" / "handoff-guard.py").is_file():
        raise HarnessError("target source tree is missing byte-stack plugin files")
    if rounds < 1 or warmup < 0:
        raise HarnessError("invalid sampling rounds or warmup count")

    selected = tuple(selected_groups)
    if not selected:
        raise HarnessError("no benchmark groups selected")
    for group in selected:
        if group not in GROUPS:
            raise HarnessError("unknown benchmark group")

    counts = dict(SAMPLE_COUNTS if _sample_counts is None else _sample_counts)
    for group in selected:
        n = counts.get(group)
        if not isinstance(n, int) or n < 1 or n % rounds != 0:
            raise HarnessError("sample count must be divisible by rounds")

    hyperfine_exe = _require_hyperfine()
    ru = build_ru(run_dir / "bin")
    _require_ru_executable(ru)
    expected = _load_expected()
    pin_prefix = _taskset_prefix()

    fx_dir = run_dir / "fixtures"
    work_dir = run_dir / "work"
    raw_dir = run_dir / "raw"
    fixtures.build(fx_dir)
    fixtures.materialize(fx_dir, work_dir, src)

    specs = build_specs(src, work_dir, selected)
    if not specs:
        raise HarnessError("no benchmarks matched selected groups")

    # Untimed digest check before sampling.
    before_ok = _check_digests(specs, expected, work_dir, src)

    accum: dict[str, dict[str, list]] = {
        spec.name: {"wall_ms": [], "cpu_ms": [], "rss_kb": [], "io_bytes": [], "exits": []}
        for spec in specs
    }

    count = len(specs)
    for r in range(rounds):
        start = r % count
        rotated = specs[start:] + specs[:start]
        for spec in rotated:
            runs_per_round = counts[spec.group] // rounds
            warm = min(warmup, 1) if spec.group == "SUITE" else warmup
            json_out = raw_dir / f"r{r}-{spec.name}.json"
            ru_out = raw_dir / f"r{r}-{spec.name}.ru"
            wall_ms, ru_rows = _run_hyperfine_round(
                hyperfine_exe,
                pin_prefix,
                ru,
                spec.argv,
                cwd=spec.cwd,
                env=spec.env,
                runs=runs_per_round,
                warmup=warm,
                json_out=json_out,
                ru_out=ru_out,
                stdin_file=spec.stdin_file,
                prepare_cmd=spec.prepare_cmd,
            )
            bucket = accum[spec.name]
            bucket["wall_ms"].extend(wall_ms)
            for utime_us, stime_us, maxrss_kb, rchar, wchar, _syscr, rc in ru_rows:
                bucket["cpu_ms"].append((utime_us + stime_us) / 1000.0)
                bucket["rss_kb"].append(maxrss_kb)
                bucket["io_bytes"].append(rchar + wchar)
                bucket["exits"].append(rc)

    # Untimed digest check after sampling.
    after_ok = _check_digests(specs, expected, work_dir, src)

    results: dict[str, dict] = {}
    for spec in specs:
        exp_rc = expected[spec.name]["exit_code"]
        bucket = accum[spec.name]
        results[spec.name] = {
            "group": spec.group,
            "wall_ms": bucket["wall_ms"],
            "cpu_ms": bucket["cpu_ms"],
            "rss_kb": bucket["rss_kb"],
            "io_bytes": bucket["io_bytes"],
            "exit_ok": all(rc == exp_rc for rc in bucket["exits"]),
            "digest_ok": before_ok[spec.name] and after_ok[spec.name],
        }
    return results


def canaries(run_dir: Path) -> dict[str, float]:
    """Measure host canary benchmarks (`ru true` and `python3 -I -c pass`) and return p50 wall ms."""
    run_dir = Path(run_dir).resolve()
    hyperfine_exe = _require_hyperfine()
    ru = build_ru(run_dir / "bin")
    _require_ru_executable(ru)
    pin_prefix = _taskset_prefix()
    canary_dir = run_dir / "canaries"
    canary_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)

    true_wall, _ = _run_hyperfine_round(
        hyperfine_exe,
        pin_prefix,
        ru,
        ("true",),
        cwd=canary_dir,
        env=env,
        runs=_CANARY_RUNS,
        warmup=_CANARY_WARMUP,
        json_out=canary_dir / "ru-true.json",
        ru_out=canary_dir / "ru-true.ru",
    )
    py_wall, _ = _run_hyperfine_round(
        hyperfine_exe,
        pin_prefix,
        ru,
        (sys.executable, "-I", "-c", "pass"),
        cwd=canary_dir,
        env=env,
        runs=_CANARY_RUNS,
        warmup=_CANARY_WARMUP,
        json_out=canary_dir / "python-startup.json",
        ru_out=canary_dir / "python-startup.ru",
    )
    return {
        "ru_true_p50_ms": float(statistics.median(true_wall)),
        "python_startup_p50_ms": float(statistics.median(py_wall)),
    }
