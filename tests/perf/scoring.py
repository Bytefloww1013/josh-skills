"""Pure scoring, quantile CI, calibration, and comparison rules for byte-stack perf."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
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

METRIC_SAMPLE_FIELD: Mapping[str, str] = {
    "L": "wall_ms",
    "U": "cpu_ms",
    "M": "rss_kb",
    "IO": "io_bytes",
}

ALL_CATEGORIES: tuple[tuple[str, str], ...] = tuple(
    (group, metric) for group in GROUPS for metric in METRICS
)


@dataclass(frozen=True)
class Readings:
    point: float
    opt: float
    pes: float


@dataclass(frozen=True)
class DetectionLimit:
    points: float
    factor: float
    pct: float


@dataclass(frozen=True)
class CategoryScore:
    group: str
    metric: str
    point: float
    opt: float
    pes: float
    error_failed: bool
    worst_benchmark: str
    gap: float
    anchor_ratio: float


@dataclass(frozen=True)
class ComparisonResult:
    regressed: tuple[tuple[str, str], ...]
    raised: tuple[tuple[str, str], ...]
    unchanged: tuple[tuple[str, str], ...]
    not_measured: tuple[tuple[str, str], ...]
    detection_limits: Mapping[tuple[str, str], DetectionLimit]
    exit_code: int


@dataclass(frozen=True)
class PairViolation:
    category: tuple[str, str]
    run_i: int
    run_j: int
    opt_i: float
    point_j: float
    eps: float


def _check_finite_numbers(values: Sequence[float]) -> list[float]:
    if not values:
        raise ValueError("sample sequence must be non-empty")
    out: list[float] = []
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError("sample values must be finite numbers")
        out.append(float(v))
    return out


def quantile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile using 0-based h = q * (n - 1)."""
    if not (0.0 <= q <= 1.0):
        raise ValueError("quantile q must be in [0, 1]")
    xs = sorted(_check_finite_numbers(values))
    n = len(xs)
    if n == 1:
        return xs[0]
    h = q * (n - 1)
    lo = math.floor(h)
    hi = lo + 1
    if hi >= n:
        return xs[-1]
    frac = h - lo
    return xs[lo] + frac * (xs[hi] - xs[lo])


def _binom_pmf(n: int, k: int, q: float) -> float:
    log_p = (
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + k * math.log(q)
        + (n - k) * math.log(1.0 - q)
    )
    return math.exp(log_p)


@lru_cache(maxsize=64)
def ci_order_statistics(n: int, q: float = 0.95, alpha: float = 0.05) -> tuple[int, int]:
    """Return 1-based (l, u) order statistics for the distribution-free (1-alpha) CI of quantile q."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("sample count n must be a positive integer")
    if not (0.0 < q < 1.0) or not (0.0 < alpha < 1.0):
        raise ValueError("q and alpha must lie strictly in (0, 1)")

    half = alpha / 2.0
    pmfs = [_binom_pmf(n, k, q) for k in range(n + 1)]

    # l (1-based): largest l in 1..n such that P(X <= l - 1) <= alpha / 2.
    lower_candidates: list[int] = []
    acc = 0.0
    for k in range(n):
        acc += pmfs[k]
        if acc <= half:
            lower_candidates.append(k + 1)
    if not lower_candidates:
        raise ValueError("sample size too small for lower confidence bound")
    l_idx = lower_candidates[-1]

    # u (1-based): smallest u in 1..n such that P(X >= u) <= alpha / 2.
    upper_candidates: list[int] = []
    tail = 0.0
    for k in range(n, 0, -1):
        tail += pmfs[k]
        if tail <= half:
            upper_candidates.append(k)
    if not upper_candidates:
        raise ValueError("sample size too small for upper confidence bound")
    u_idx = upper_candidates[-1]

    if l_idx > u_idx:
        raise ValueError("invalid confidence interval bounds")
    return l_idx, u_idx


def metric_readings(values: Sequence[float], metric: str) -> Readings:
    """Compute (point, opt, pes) readings for one benchmark and metric."""
    if metric not in METRICS:
        raise ValueError("unknown metric")
    xs = sorted(_check_finite_numbers(values))
    if metric == "IO":
        med = quantile(xs, 0.50)
        return Readings(point=med, opt=med, pes=med)
    point = quantile(xs, 0.95)
    l_idx, u_idx = ci_order_statistics(len(xs))
    return Readings(point=point, opt=xs[l_idx - 1], pes=xs[u_idx - 1])


def subscore(value: float, g: float, k: float) -> float:
    """Normalized 0-100 log-scale sub-score: 100 * clamp(ln(k/v) / ln(k/g), 0, 1)."""
    if (
        isinstance(value, bool)
        or isinstance(g, bool)
        or isinstance(k, bool)
        or not (math.isfinite(value) and math.isfinite(g) and math.isfinite(k))
    ):
        raise ValueError("subscore inputs must be finite numbers")
    if g <= 0.0 or k <= g:
        raise ValueError("anchors must satisfy 0 < g < k")
    if value <= g:
        return 100.0
    if value >= k:
        return 0.0
    raw = math.log(k / value) / math.log(k / g)
    clamped = min(1.0, max(0.0, raw))
    return 100.0 * clamped


def score_samples(
    samples: Mapping[str, Mapping[str, object]],
    anchors: Mapping[str, Mapping[str, Mapping[str, float]]],
    groups: Sequence[str],
) -> dict[tuple[str, str], CategoryScore]:
    """Score every category (g, m) for the requested groups."""
    by_group: dict[str, list[tuple[str, Mapping[str, object]]]] = {g: [] for g in groups}
    for bench_name, data in samples.items():
        grp = data.get("group")
        if grp in by_group:
            by_group[str(grp)].append((bench_name, data))

    results: dict[tuple[str, str], CategoryScore] = {}
    for group in groups:
        benches = sorted(by_group[group], key=lambda item: item[0])
        if not benches:
            raise ValueError("missing benchmarks for group")
        for metric in METRICS:
            field = METRIC_SAMPLE_FIELD[metric]
            point_scores: list[tuple[float, str, float, float]] = []
            opt_scores: list[float] = []
            pes_scores: list[float] = []
            any_error = False

            for bench_name, data in benches:
                if bench_name not in anchors or metric not in anchors[bench_name]:
                    raise ValueError("missing calibration anchor for benchmark")
                anchor = anchors[bench_name][metric]
                g_val = float(anchor["g"])
                k_val = float(anchor["k"])
                if g_val <= 0.0 or k_val <= g_val:
                    raise ValueError("invalid calibration anchor")

                exit_ok = bool(data.get("exit_ok"))
                digest_ok = bool(data.get("digest_ok"))
                e_ok = exit_ok and digest_ok
                if not e_ok:
                    any_error = True

                raw_vals = data.get(field)
                if not isinstance(raw_vals, Sequence):
                    raise ValueError("missing metric sample array")
                readings = metric_readings(raw_vals, metric)

                if e_ok:
                    s_pt = subscore(readings.point, g_val, k_val)
                    s_opt = subscore(readings.opt, g_val, k_val)
                    s_pes = subscore(readings.pes, g_val, k_val)
                else:
                    s_pt = 0.0
                    s_opt = 0.0
                    s_pes = 0.0

                gap = max(0.0, s_opt - s_pt)
                point_scores.append((s_pt, bench_name, gap, k_val / g_val))
                opt_scores.append(s_opt)
                pes_scores.append(s_pes)

            worst_pt, worst_name, _, _ = min(point_scores, key=lambda item: (item[0], item[1]))
            # Use the largest gap and largest anchor ratio across the group so the reported
            # detection limit upper-bounds every benchmark in the category.
            max_gap = max(item[2] for item in point_scores)
            max_ratio = max(item[3] for item in point_scores)

            results[(group, metric)] = CategoryScore(
                group=group,
                metric=metric,
                point=0.0 if any_error else worst_pt,
                opt=0.0 if any_error else min(opt_scores),
                pes=0.0 if any_error else min(pes_scores),
                error_failed=any_error,
                worst_benchmark=worst_name,
                gap=max_gap,
                anchor_ratio=max_ratio,
            )
    return results


def composite_score(
    category_points: Mapping[tuple[str, str], float],
    group_weights: Mapping[str, float],
    metric_weights: Mapping[str, float],
    selected: Sequence[tuple[str, str]] | None = None,
) -> tuple[float, float]:
    """Return (composite, selected_weight). For partial selections, composite is normalized by selected_weight."""
    cats = list(ALL_CATEGORIES if selected is None else selected)
    if not cats:
        raise ValueError("selected categories must be non-empty")
    weighted_sum = 0.0
    total_weight = 0.0
    for group, metric in cats:
        w = float(group_weights[group]) * float(metric_weights[metric])
        weighted_sum += w * float(category_points[(group, metric)])
        total_weight += w
    if total_weight <= 0.0:
        raise ValueError("total category weight must be positive")
    if len(cats) == len(ALL_CATEGORIES) and math.isclose(total_weight, 1.0, rel_tol=1e-9, abs_tol=1e-9):
        return weighted_sum, 1.0
    return weighted_sum / total_weight, total_weight


def composite_from_nested(
    nested_categories: Mapping[str, Mapping[str, float]],
    group_weights: Mapping[str, float],
    metric_weights: Mapping[str, float],
) -> float:
    """Compute the full 32-category composite score from baseline-style nested dict."""
    flat = {
        (g, m): float(nested_categories[g][m])
        for g in GROUPS
        for m in METRICS
    }
    comp, _ = composite_score(flat, group_weights, metric_weights)
    return comp


def detection_limit(eps_c: float, gap: float, anchor_ratio: float) -> DetectionLimit:
    """Category detection limit: slowdown factor (k/g)^((eps + gap)/100)."""
    pts = float(eps_c) + max(0.0, float(gap))
    factor = float(anchor_ratio) ** (pts / 100.0)
    pct = (factor - 1.0) * 100.0
    return DetectionLimit(points=pts, factor=factor, pct=pct)


def compare_against_baseline(
    scored: Mapping[tuple[str, str], CategoryScore],
    marks: Mapping[str, Mapping[str, float]],
    eps: Mapping[str, Mapping[str, float]],
    selected: Sequence[tuple[str, str]],
) -> ComparisonResult:
    """Apply Rule 3 (regression) and Rules 6-7 (overwrite eligibility) to selected categories."""
    selected_set = set(selected)
    regressed: list[tuple[str, str]] = []
    raised: list[tuple[str, str]] = []
    unchanged: list[tuple[str, str]] = []
    not_measured: list[tuple[str, str]] = []
    limits: dict[tuple[str, str], DetectionLimit] = {}

    for cat in ALL_CATEGORIES:
        group, metric = cat
        if cat not in selected_set:
            not_measured.append(cat)
            continue
        cs = scored[cat]
        h_c = float(marks[group][metric])
        eps_c = float(eps[group][metric])
        limits[cat] = detection_limit(eps_c, cs.gap, cs.anchor_ratio)

        if cs.error_failed or cs.opt < h_c - eps_c:
            regressed.append(cat)
        elif cs.pes > h_c + eps_c:
            raised.append(cat)
        else:
            unchanged.append(cat)

    if regressed:
        # Never raise any mark when any category regressed.
        unchanged.extend(raised)
        unchanged.sort(key=ALL_CATEGORIES.index)
        raised = []
        exit_code = 1
    else:
        exit_code = 0

    return ComparisonResult(
        regressed=tuple(regressed),
        raised=tuple(raised),
        unchanged=tuple(unchanged),
        not_measured=tuple(not_measured),
        detection_limits=limits,
        exit_code=exit_code,
    )


def compute_anchors(
    runs: Sequence[Mapping[str, Mapping[str, object]]],
    g_p50_mult: float,
    k_p95_mult: float,
) -> dict[str, dict[str, dict[str, float]]]:
    """Compute per-benchmark per-metric anchors g = g_p50_mult * p50, k = k_p95_mult * p95."""
    if not runs:
        raise ValueError("calibration requires at least one run")
    bench_names = sorted(runs[0].keys())
    if not bench_names:
        raise ValueError("calibration run has no benchmarks")

    anchors: dict[str, dict[str, dict[str, float]]] = {}
    for bench_name in bench_names:
        anchors[bench_name] = {}
        for metric in METRICS:
            field = METRIC_SAMPLE_FIELD[metric]
            pooled: list[float] = []
            for run in runs:
                if bench_name not in run:
                    raise ValueError("inconsistent benchmark set across calibration runs")
                data = run[bench_name]
                if not bool(data.get("exit_ok")) or not bool(data.get("digest_ok")):
                    raise ValueError("calibration benchmark failed error gate")
                raw_vals = data.get(field)
                if not isinstance(raw_vals, Sequence):
                    raise ValueError("missing metric sample array")
                pooled.extend(_check_finite_numbers(raw_vals))
            p50 = quantile(pooled, 0.50)
            p95 = quantile(pooled, 0.95)
            g_val = g_p50_mult * p50
            k_val = k_p95_mult * p95
            if g_val <= 0.0 or k_val <= g_val:
                raise ValueError("degenerate calibration anchors")
            anchors[bench_name][metric] = {"g": g_val, "k": k_val}
    return anchors


def compute_eps(
    run_scores: Sequence[Mapping[tuple[str, str], CategoryScore]],
    eps_min: float = 2.0,
    iqr_fence: float = 1.5,
) -> dict[str, dict[str, float]]:
    """Compute Tukey fence tolerance eps_c = max(eps_min, iqr_fence * IQR(C^point))."""
    if len(run_scores) < 2:
        raise ValueError("calibration requires at least two runs")
    eps: dict[str, dict[str, float]] = {g: {} for g in GROUPS}
    for group in GROUPS:
        for metric in METRICS:
            pts = [rs[(group, metric)].point for rs in run_scores]
            iqr = quantile(pts, 0.75) - quantile(pts, 0.25)
            eps[group][metric] = max(float(eps_min), float(iqr_fence) * iqr)
    return eps


def check_calibration_pairs(
    run_scores: Sequence[Mapping[tuple[str, str], CategoryScore]],
    eps: Mapping[str, Mapping[str, float]],
) -> list[PairViolation]:
    """Check every ordered pair (i, j) for C^opt_{c,i} < C^point_{c,j} - eps_c."""
    violations: list[PairViolation] = []
    k_runs = len(run_scores)
    for cat in ALL_CATEGORIES:
        group, metric = cat
        eps_c = float(eps[group][metric])
        for i in range(k_runs):
            opt_i = run_scores[i][cat].opt
            for j in range(k_runs):
                if i == j:
                    continue
                point_j = run_scores[j][cat].point
                if opt_i < point_j - eps_c:
                    violations.append(
                        PairViolation(
                            category=cat,
                            run_i=i,
                            run_j=j,
                            opt_i=opt_i,
                            point_j=point_j,
                            eps=eps_c,
                        )
                    )
    return violations


def parse_selectors(raw: str) -> tuple[tuple[str, str], ...]:
    """Parse --only comma-separated selectors into canonical ordered (group, metric) pairs."""
    if not raw or not raw.strip():
        raise ValueError("empty selector")
    selected: set[tuple[str, str]] = set()
    for part in raw.split(","):
        token = part.strip()
        if not token:
            raise ValueError("empty selector item")
        if "." in token:
            pieces = token.split(".")
            if len(pieces) != 2:
                raise ValueError("invalid category selector")
            grp, met = pieces
            if grp not in GROUPS or met not in METRICS:
                raise ValueError("unknown category selector")
            selected.add((grp, met))
        else:
            if token not in GROUPS:
                raise ValueError("unknown group selector")
            for met in METRICS:
                selected.add((token, met))
    return tuple(cat for cat in ALL_CATEGORIES if cat in selected)


def groups_for_categories(categories: Sequence[tuple[str, str]]) -> tuple[str, ...]:
    """Return unique groups referenced by categories in canonical GROUPS order."""
    present = {group for group, _ in categories}
    return tuple(group for group in GROUPS if group in present)
