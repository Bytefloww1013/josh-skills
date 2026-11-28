"""Host fingerprint and toolchain metadata for byte-stack perf scan."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Callable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from benchmarks import HarnessError

_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("model name"):
                _, _, value = line.partition(":")
                cleaned = " ".join(value.split())
                if cleaned:
                    return cleaned
    except OSError:
        pass
    return " ".join(platform.processor().split()) or platform.machine() or "unknown"


def _governor() -> str:
    gov_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    try:
        text = gov_path.read_text(encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass
    return "unknown"


def _kernel_major() -> str:
    release = platform.release().strip()
    major = release.split(".", 1)[0]
    return major if major.isdigit() else "unknown"


def _python_version() -> str:
    v = sys.version_info
    return f"{v.major}.{v.minor}.{v.micro}"


def _hyperfine_version() -> str:
    exe = shutil.which("hyperfine")
    if not exe:
        raise HarnessError("hyperfine is unavailable")
    try:
        proc = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise HarnessError("failed to query hyperfine version") from exc
    if proc.returncode != 0:
        raise HarnessError("failed to query hyperfine version")
    match = _VERSION_RE.search(proc.stdout)
    if not match:
        raise HarnessError("unrecognized hyperfine version output")
    return match.group(1)


def _parse_cpu_list(text: str) -> set[int]:
    cpus: set[int] = set()
    for part in text.strip().split(","):
        lo, _, hi = part.partition("-")
        if lo.isdigit() and (not hi or hi.isdigit()):
            cpus.update(range(int(lo), int(hi or lo) + 1))
    return cpus


def _thread_siblings(cpu: int) -> set[int]:
    path = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list")
    try:
        return _parse_cpu_list(path.read_text(encoding="utf-8")) | {cpu}
    except OSError:
        return {cpu}


def _max_freq_khz(cpu: int) -> int:
    path = Path(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/cpuinfo_max_freq")
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return 0
    return int(text) if text.isdigit() else 0


def pin_cpu(
    interrupts_text: str | None = None,
    allowed: set[int] | None = None,
    siblings: Callable[[int], set[int]] = _thread_siblings,
    max_freq: Callable[[int], int] = _max_freq_khz,
) -> int:
    """Return the CPU the benchmarks are pinned to.

    PERF_PIN_CPU overrides the choice. Otherwise, among the allowed CPUs of the fastest core
    type (highest cpuinfo_max_freq, so performance cores on a hybrid CPU), pick the one whose
    physical core (the CPU and its SMT siblings) has handled the fewest device interrupts
    (the numbered lines of /proc/interrupts); on a tie, the highest-numbered one, since
    CPU 0 usually carries the most housekeeping work.
    """
    if allowed is None:
        allowed = set(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else {0}
    if not allowed:
        raise HarnessError("no CPU is available to pin benchmarks to")
    override = os.environ.get("PERF_PIN_CPU")
    if override is not None:
        if not override.isdigit() or int(override) not in allowed:
            raise HarnessError("PERF_PIN_CPU is not an available CPU")
        return int(override)
    freqs = {cpu: max_freq(cpu) for cpu in allowed}
    fastest = max(freqs.values())
    allowed = {cpu for cpu in allowed if freqs[cpu] == fastest}
    if interrupts_text is None:
        try:
            interrupts_text = Path("/proc/interrupts").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return max(allowed)
    lines = interrupts_text.splitlines()
    if not lines:
        return max(allowed)
    columns = [int(tok[3:]) for tok in lines[0].split() if tok.startswith("CPU") and tok[3:].isdigit()]
    per_cpu: dict[int, int] = {}
    for line in lines[1:]:
        label, _, rest = line.partition(":")
        if not label.strip().isdigit():
            continue
        values = rest.split()
        for cpu, tok in zip(columns, values):
            if tok.isdigit():
                per_cpu[cpu] = per_cpu.get(cpu, 0) + int(tok)
    counts = {cpu: sum(per_cpu.get(sib, 0) for sib in siblings(cpu)) for cpu in allowed}
    return min(counts, key=lambda cpu: (counts[cpu], -cpu))


def fingerprint() -> str:
    """Return 64-hex SHA-256 of host hardware/toolchain identity (never hostname or username)."""
    override = os.environ.get("PERF_FINGERPRINT_OVERRIDE")
    if override is not None:
        return hashlib.sha256(override.encode("utf-8")).hexdigest()
    payload = {
        "cpu_model": _cpu_model(),
        "core_count": os.cpu_count() or 0,
        "governor": _governor(),
        "kernel_major": _kernel_major(),
        "python": _python_version(),
        "hyperfine": _hyperfine_version(),
        "pin_cpu": pin_cpu(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def toolchain(ru: Path) -> dict[str, str]:
    """Return toolchain versions and SHA-256 digest of the compiled ru helper."""
    ru_path = Path(ru)
    try:
        if not ru_path.is_file():
            raise HarnessError("ru helper binary is missing")
        ru_sha256 = hashlib.sha256(ru_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise HarnessError("ru helper binary is unreadable") from exc
    return {
        "python": _python_version(),
        "hyperfine": _hyperfine_version(),
        "ru_sha256": ru_sha256,
    }
