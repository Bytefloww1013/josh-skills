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
