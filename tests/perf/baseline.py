"""Baseline, calibration, config, schema validation, and atomic persistence."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any, Mapping, Sequence

PERF_DIR = Path(__file__).resolve().parent
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

import scoring

CONFIG_PATH = PERF_DIR / "config.json"
BASELINE_SCHEMA_PATH = PERF_DIR / "baseline.schema.json"

_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)


class StateError(Exception):
    """Fixed-text error for state, config, calibration, or baseline failures."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state_dir_from_env(env: Mapping[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    xdg = source.get("XDG_STATE_HOME", "").strip()
    base = Path(xdg) if xdg else (Path.home() / ".local" / "state")
    return base / "byte-stack-perf"


def baseline_path(state_dir: Path) -> Path:
    return state_dir / "baseline.json"


def calibration_path(state_dir: Path) -> Path:
    return state_dir / "calibration.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_run_dir(state_dir: Path) -> Path:
    runs_root = state_dir / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = runs_root / stamp
    suffix = 1
    while candidate.exists():
        candidate = runs_root / f"{stamp}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def prune_run_dirs(state_dir: Path, keep: int = 3) -> None:
    runs_root = state_dir / "runs"
    if not runs_root.is_dir():
        return
    entries = sorted(
        (p for p in runs_root.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    for stale in entries[keep:]:
        shutil.rmtree(stale, ignore_errors=True)


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write JSON to a temp file in the same directory, fsync, and os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _resolve_ref(ref: str, root_schema: Mapping[str, Any]) -> Mapping[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError("unsupported schema reference")
    node: Any = root_schema
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _is_valid_datetime(value: str) -> bool:
    if not _RFC3339_RE.match(value):
        return False
    normalized = value[:-1] + "+00:00" if value[-1] in ("Z", "z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


def validate_against_schema(
    instance: Any,
    schema: Mapping[str, Any],
    *,
    root_schema: Mapping[str, Any] | None = None,
    location: str = "$",
) -> list[str]:
    """Validate an instance against the JSON Schema subset used by baseline.schema.json."""
    root = schema if root_schema is None else root_schema
    if "$ref" in schema:
        schema = _resolve_ref(schema["$ref"], root)

    errors: list[str] = []

    if "const" in schema:
        const_val = schema["const"]
        if type(instance) is not type(const_val) or instance != const_val:
            errors.append(f"{location}: const mismatch")
            return errors

    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(instance, dict):
            return [f"{location}: expected object"]
    elif expected_type == "integer":
        if isinstance(instance, bool) or not isinstance(instance, int):
            return [f"{location}: expected integer"]
    elif expected_type == "number":
        if isinstance(instance, bool) or not isinstance(instance, (int, float)) or not math.isfinite(instance):
            return [f"{location}: expected finite number"]
    elif expected_type == "string":
        if not isinstance(instance, str):
            return [f"{location}: expected string"]
    elif expected_type == "array":
        if not isinstance(instance, list):
            return [f"{location}: expected array"]
    elif expected_type == "boolean":
        if not isinstance(instance, bool):
            return [f"{location}: expected boolean"]

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{location}: below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{location}: above maximum")

    if isinstance(instance, str):
        if "pattern" in schema:
            pat = schema["pattern"]
            if pat.startswith("^") and pat.endswith("$"):
                matched = re.fullmatch(pat[1:-1], instance) is not None
            else:
                matched = re.search(pat, instance) is not None
            if not matched:
                errors.append(f"{location}: pattern mismatch")
        if schema.get("format") == "date-time" and not _is_valid_datetime(instance):
            errors.append(f"{location}: invalid date-time format")

    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for req_key in schema.get("required", []):
            if req_key not in instance:
                errors.append(f"{location}: missing required property {req_key}")
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    errors.append(f"{location}: unexpected property {key}")
        for key, sub_schema in props.items():
            if key in instance:
                errors.extend(
                    validate_against_schema(
                        instance[key],
                        sub_schema,
                        root_schema=root,
                        location=f"{location}.{key}",
                    )
                )

    return errors


def load_schema(path: Path = BASELINE_SCHEMA_PATH) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError("invalid baseline schema file") from exc
    if not isinstance(data, dict):
        raise StateError("invalid baseline schema file")
    return data


def validate_baseline(record: Any, schema: Mapping[str, Any] | None = None) -> None:
    active_schema = load_schema() if schema is None else schema
    errors = validate_against_schema(record, active_schema)
    if errors:
        raise StateError("invalid baseline record")


def load_config(path: Path = CONFIG_PATH) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        cfg = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateError("invalid config file") from exc

    if not isinstance(cfg, dict):
        raise StateError("invalid config file")
    required = {
        "config_version",
        "rounds",
        "warmup",
        "anchor_multipliers",
        "eps",
        "host_gate",
        "keep_runs",
        "metric_weights",
        "groups",
    }
    if not required.issubset(cfg.keys()):
        raise StateError("invalid config file")

    groups = cfg["groups"]
    metric_weights = cfg["metric_weights"]
    if not isinstance(groups, dict) or set(groups.keys()) != set(scoring.GROUPS):
        raise StateError("invalid config file")
    if not isinstance(metric_weights, dict) or set(metric_weights.keys()) != set(scoring.METRICS):
        raise StateError("invalid config file")

    for g in scoring.GROUPS:
        entry = groups[g]
        if not isinstance(entry, dict) or "weight" not in entry or "n" not in entry:
            raise StateError("invalid config file")
        if isinstance(entry["n"], bool) or not isinstance(entry["n"], int) or entry["n"] < 1:
            raise StateError("invalid config file")
        if isinstance(entry["weight"], bool) or not isinstance(entry["weight"], (int, float)) or entry["weight"] <= 0:
            raise StateError("invalid config file")

    if not math.isclose(sum(groups[g]["weight"] for g in scoring.GROUPS), 1.0, abs_tol=1e-6):
        raise StateError("invalid config file")
    if not math.isclose(sum(metric_weights[m] for m in scoring.METRICS), 1.0, abs_tol=1e-6):
        raise StateError("invalid config file")

    return cfg, hashlib.sha256(raw).hexdigest()


def validate_calibration(data: Any) -> None:
    if not isinstance(data, dict):
        raise StateError("invalid calibration file")
    required = {"schema_version", "host_fingerprint", "canaries", "anchors", "eps"}
    if not required.issubset(data.keys()):
        raise StateError("invalid calibration file")
    if data.get("schema_version") != 1 or isinstance(data.get("schema_version"), bool):
        raise StateError("invalid calibration file")
    fp = data.get("host_fingerprint")
    if not isinstance(fp, str) or re.fullmatch(r"[0-9a-f]{64}", fp) is None:
        raise StateError("invalid calibration file")
    canaries = data.get("canaries")
    if not isinstance(canaries, dict) or not canaries:
        raise StateError("invalid calibration file")
    for val in canaries.values():
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val <= 0:
            raise StateError("invalid calibration file")
    anchors = data.get("anchors")
    if not isinstance(anchors, dict) or not anchors:
        raise StateError("invalid calibration file")
    for bench_anchors in anchors.values():
        if not isinstance(bench_anchors, dict) or set(bench_anchors.keys()) != set(scoring.METRICS):
            raise StateError("invalid calibration file")
        for m in scoring.METRICS:
            pair = bench_anchors[m]
            if not isinstance(pair, dict) or "g" not in pair or "k" not in pair:
                raise StateError("invalid calibration file")
            g_val, k_val = pair["g"], pair["k"]
            if (
                isinstance(g_val, bool)
                or isinstance(k_val, bool)
                or not isinstance(g_val, (int, float))
                or not isinstance(k_val, (int, float))
                or not (math.isfinite(g_val) and math.isfinite(k_val))
                or g_val <= 0
                or k_val <= g_val
            ):
                raise StateError("invalid calibration file")
    eps = data.get("eps")
    if not isinstance(eps, dict) or set(eps.keys()) != set(scoring.GROUPS):
        raise StateError("invalid calibration file")
    for g in scoring.GROUPS:
        if not isinstance(eps[g], dict) or set(eps[g].keys()) != set(scoring.METRICS):
            raise StateError("invalid calibration file")
        for m in scoring.METRICS:
            val = eps[g][m]
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val < 0:
                raise StateError("invalid calibration file")


def load_calibration(state_dir: Path) -> tuple[dict[str, Any], str]:
    path = calibration_path(state_dir)
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateError("missing or invalid calibration file") from exc
    validate_calibration(data)
    return data, hashlib.sha256(raw).hexdigest()


def save_calibration(state_dir: Path, data: Mapping[str, Any]) -> None:
    validate_calibration(data)
    atomic_write_json(calibration_path(state_dir), data)


def load_baseline(state_dir: Path) -> dict[str, Any]:
    path = baseline_path(state_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError("missing or invalid baseline file") from exc
    validate_baseline(data)
    return data


def save_baseline(state_dir: Path, record: Mapping[str, Any]) -> None:
    validate_baseline(record)
    atomic_write_json(baseline_path(state_dir), record)


def build_baseline_record(
    *,
    config: Mapping[str, Any],
    commit: str,
    config_sha256: str,
    calibration_sha256: str,
    fixtures_sha256: str,
    host_fingerprint: str,
    toolchain: Mapping[str, Any],
    categories: Mapping[str, Mapping[str, float]],
    verified_at: str | None = None,
) -> dict[str, Any]:
    group_weights = {g: float(config["groups"][g]["weight"]) for g in scoring.GROUPS}
    metric_weights = {m: float(config["metric_weights"][m]) for m in scoring.METRICS}
    ordered_categories = {
        g: {m: float(categories[g][m]) for m in scoring.METRICS}
        for g in scoring.GROUPS
    }
    composite = scoring.composite_from_nested(ordered_categories, group_weights, metric_weights)
    record = {
        "schema_version": 1,
        "config_version": int(config["config_version"]),
        "commit": commit,
        "config_sha256": config_sha256,
        "calibration_sha256": calibration_sha256,
        "fixtures_sha256": fixtures_sha256,
        "host_fingerprint": host_fingerprint,
        "toolchain": {
            "python": str(toolchain["python"]),
            "hyperfine": str(toolchain["hyperfine"]),
            "ru_sha256": str(toolchain["ru_sha256"]),
        },
        "verified_at": utc_now_iso() if verified_at is None else verified_at,
        "composite": composite,
        "categories": ordered_categories,
    }
    validate_baseline(record)
    return record


def update_baseline_record(
    existing: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    scored: Mapping[tuple[str, str], scoring.CategoryScore],
    raised: Sequence[tuple[str, str]],
    commit: str,
    verified_at: str | None = None,
) -> dict[str, Any]:
    """Raise only the confident improvements; preserve every other mark verbatim."""
    new_categories: dict[str, dict[str, float]] = {
        g: {m: existing["categories"][g][m] for m in scoring.METRICS}
        for g in scoring.GROUPS
    }
    for group, metric in raised:
        new_categories[group][metric] = scored[(group, metric)].point

    group_weights = {g: float(config["groups"][g]["weight"]) for g in scoring.GROUPS}
    metric_weights = {m: float(config["metric_weights"][m]) for m in scoring.METRICS}
    composite = scoring.composite_from_nested(new_categories, group_weights, metric_weights)

    updated = {
        "schema_version": existing["schema_version"],
        "config_version": existing["config_version"],
        "commit": commit,
        "config_sha256": existing["config_sha256"],
        "calibration_sha256": existing["calibration_sha256"],
        "fixtures_sha256": existing["fixtures_sha256"],
        "host_fingerprint": existing["host_fingerprint"],
        "toolchain": dict(existing["toolchain"]),
        "verified_at": utc_now_iso() if verified_at is None else verified_at,
        "composite": composite,
        "categories": new_categories,
    }
    validate_baseline(updated)
    return updated
