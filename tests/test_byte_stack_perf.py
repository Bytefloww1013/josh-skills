"""Unit tests for tests/perf scoring, baseline policy, schema, and scan CLI."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PERF_DIR = ROOT / "tests" / "perf"
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

import baseline
import scan
import scoring

FAKE_FP = "a" * 64
FAKE_FX_SHA = "b" * 64
FAKE_RU_SHA = "c" * 64
FAKE_TOOLCHAIN = {
    "python": "3.14.4",
    "hyperfine": "1.19.0",
    "ru_sha256": FAKE_RU_SHA,
}
FAKE_CANARIES = {
    "ru_true_p50_ms": 1.0,
    "python_startup_p50_ms": 12.7,
}

# Realistic group -> benchmark catalog (including 8 benchmarks in HOOK_HOT).
BENCHMARKS_BY_GROUP: dict[str, tuple[str, ...]] = {
    "HOOK_HOT": (
        "pre.off.4m",
        "post.off.64k",
        "post.off.1m",
        "post.off.4m-noboundary",
        "post.off.8m-boundary",
        "prompt.off.4m",
        "pre.pending.4m",
        "noop.handoff0",
    ),
    "HOOK_LIFECYCLE": (
        "precompact.auto.defer",
        "precompact.auto.done",
        "sessionstart.compact.paste",
    ),
    "ASSETS": (
        "assets.list-playbooks",
        "assets.list-references",
        "assets.resolve-feature",
        "assets.resolve-override",
    ),
    "BRIEFS": (
        "briefs.fill-reviewer",
        "briefs.keys-implementor",
        "briefs.check-report",
    ),
    "CAPTURE": (
        "capture.schema",
        "capture.validate",
        "capture.write-dry-run",
    ),
    "EXTRACT": (
        "extract.inventory",
        "extract.write-dry-run",
    ),
    "INIT": (
        "init.fresh-repo",
    ),
    "SUITE": (
        "suite.check-handoff-guard",
    ),
}

BASE_METRICS = {
    "wall_ms": 40.0,
    "cpu_ms": 38.0,
    "rss_kb": 16000,
    "io_bytes": 1000000,
}


def _sample_count(group: str) -> int:
    return 100 if group == "SUITE" else 200


def _make_samples(
    selected_groups=scoring.GROUPS,
    *,
    overrides: dict[str, dict] | None = None,
    group_scale: dict[str, float] | None = None,
) -> dict[str, dict]:
    """Build deterministic synthetic measurement output matching the slice A contract."""
    overrides = overrides or {}
    group_scale = group_scale or {}
    out: dict[str, dict] = {}
    for group in selected_groups:
        n = _sample_count(group)
        scale = group_scale.get(group, 1.0)
        for bench in BENCHMARKS_BY_GROUP[group]:
            entry = {
                "group": group,
                "wall_ms": [BASE_METRICS["wall_ms"] * scale] * n,
                "cpu_ms": [BASE_METRICS["cpu_ms"] * scale] * n,
                "rss_kb": [int(round(BASE_METRICS["rss_kb"] * scale))] * n,
                "io_bytes": [int(round(BASE_METRICS["io_bytes"] * scale))] * n,
                "exit_ok": True,
                "digest_ok": True,
            }
            if bench in overrides:
                entry.update(overrides[bench])
            out[bench] = entry
    return out


class HarnessError(Exception):
    """Test stand-in for slice A's HarnessError."""


class ScoringMathTests(unittest.TestCase):
    def test_ci_order_statistics_for_100_150_200(self):
        self.assertEqual(scoring.ci_order_statistics(100), (90, 100))
        self.assertEqual(scoring.ci_order_statistics(150), (137, 148))
        self.assertEqual(scoring.ci_order_statistics(200), (184, 197))
        with self.assertRaises(ValueError):
            scoring.ci_order_statistics(50)

    def test_subscore_boundaries_and_log_scale(self):
        g, k = 15.0, 122.4
        self.assertEqual(scoring.subscore(g, g, k), 100.0)
        self.assertEqual(scoring.subscore(k, g, k), 0.0)
        # Beyond both anchors (including zero and negative values).
        self.assertEqual(scoring.subscore(g * 0.5, g, k), 100.0)
        self.assertEqual(scoring.subscore(0.0, g, k), 100.0)
        self.assertEqual(scoring.subscore(-5.0, g, k), 100.0)
        self.assertEqual(scoring.subscore(k * 2.0, g, k), 0.0)

        # Plan section 5 V2 arithmetic: g=15.0, k=122.4 -> v=30.6 ~66.0, v=80.6 ~19.9.
        self.assertAlmostEqual(scoring.subscore(30.6, g, k), 66.04, places=2)
        self.assertAlmostEqual(scoring.subscore(80.6, g, k), 19.90, places=2)

        # Log scale: a 2x slowdown costs the exact same points anywhere inside (g, k).
        drop_low = scoring.subscore(20.0, g, k) - scoring.subscore(40.0, g, k)
        drop_high = scoring.subscore(45.0, g, k) - scoring.subscore(90.0, g, k)
        self.assertAlmostEqual(drop_low, drop_high, places=9)

    def test_metric_readings_p95_ci_and_io_median(self):
        xs = [float(i + 1) for i in range(200)]
        r_lat = scoring.metric_readings(xs, "L")
        # h = 0.95 * 199 = 189.05 -> xs[189] + 0.05*(xs[190]-xs[189]) = 190.05
        self.assertAlmostEqual(r_lat.point, 190.05, places=9)
        self.assertEqual(r_lat.opt, 184.0)
        self.assertEqual(r_lat.pes, 197.0)

        r_io = scoring.metric_readings(xs, "IO")
        self.assertAlmostEqual(r_io.point, 100.5, places=9)
        self.assertEqual(r_io.opt, r_io.point)
        self.assertEqual(r_io.pes, r_io.point)

    def test_selector_parsing(self):
        self.assertEqual(
            scoring.parse_selectors("ASSETS"),
            (("ASSETS", "L"), ("ASSETS", "U"), ("ASSETS", "M"), ("ASSETS", "IO")),
        )
        self.assertEqual(scoring.parse_selectors("INIT.L"), (("INIT", "L"),))
        self.assertEqual(
            scoring.parse_selectors("INIT.L,ASSETS"),
            (
                ("ASSETS", "L"),
                ("ASSETS", "U"),
                ("ASSETS", "M"),
                ("ASSETS", "IO"),
                ("INIT", "L"),
            ),
        )
        for bad in ("", "   ", "NOPE", "INIT.", ".L", "INIT.NOPE", "INIT.L.EXTRA", "ASSETS,"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    scoring.parse_selectors(bad)

    def test_calibration_pair_check_rejects_too_tight_eps(self):
        # 8 runs: 7 tight runs at score ~66.67, 1 noisy run at score ~55.0.
        # Because only 1 of 8 is an outlier, IQR == 0, so eps = max(2.0, 1.5*0) = 2.0,
        # and the ordered-pair check must catch opt_outlier < point_normal - eps.
        normal = _make_samples()
        noisy = _make_samples(overrides={"init.fresh-repo": {"wall_ms": [55.0] * 200}})
        runs = [normal] * 7 + [noisy]
        anchors = scoring.compute_anchors(runs, 0.5, 4.0)
        run_scores = [scoring.score_samples(r, anchors, scoring.GROUPS) for r in runs]
        eps = scoring.compute_eps(run_scores, eps_min=2.0, iqr_fence=1.5)
        self.assertEqual(eps["INIT"]["L"], 2.0)

        violations = scoring.check_calibration_pairs(run_scores, eps)
        self.assertTrue(any(v.category == ("INIT", "L") for v in violations))

        # Raising eps above the gap clears the violations.
        eps_wide = copy.deepcopy(eps)
        eps_wide["INIT"]["L"] = 25.0
        self.assertEqual(scoring.check_calibration_pairs(run_scores, eps_wide), [])


class ScanCliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.xdg_state = self.temp / "xdg-state-secret-marker"
        self.xdg_state.mkdir()
        self.state_dir = self.xdg_state / "byte-stack-perf"
        self.src_dir = self.temp / "plugin-src-secret-marker"
        self.src_dir.mkdir()

        env_patch = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.xdg_state)})
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def _run_main(
        self,
        argv: list[str],
        *,
        measure=None,
        canaries=None,
        fingerprint=None,
        toolchain=None,
        build_fixtures=None,
        loadavg=None,
    ) -> tuple[int, str, str]:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            code = scan.main(
                argv,
                measure=measure if measure is not None else (lambda src, groups, rdir, **kw: _make_samples(groups)),
                canaries=canaries if canaries is not None else (lambda rdir: dict(FAKE_CANARIES)),
                fingerprint=fingerprint if fingerprint is not None else (lambda: FAKE_FP),
                toolchain=toolchain if toolchain is not None else (lambda rdir: dict(FAKE_TOOLCHAIN)),
                build_fixtures=build_fixtures if build_fixtures is not None else (lambda root: FAKE_FX_SHA),
                loadavg=loadavg if loadavg is not None else (lambda: 0.25),
                sleep=lambda seconds: None,
            )
        return code, out_buf.getvalue(), err_buf.getvalue()

    def _calibrate_and_init(self) -> bytes:
        code, _, err = self._run_main(["calibrate", "--runs", "4", "--src", str(self.src_dir)])
        self.assertEqual(code, 0, err)
        code, _, err = self._run_main(["init", "--src", str(self.src_dir)])
        self.assertEqual(code, 0, err)
        return baseline.baseline_path(self.state_dir).read_bytes()

    def _latest_report(self) -> dict:
        runs = sorted((self.state_dir / "runs").iterdir(), key=lambda p: p.name)
        self.assertTrue(runs)
        return json.loads((runs[-1] / "report.json").read_text(encoding="utf-8"))

    def test_calibrate_init_and_schema_v4(self):
        raw_baseline = self._calibrate_and_init()
        cal = json.loads(baseline.calibration_path(self.state_dir).read_text(encoding="utf-8"))
        self.assertEqual(cal["host_fingerprint"], FAKE_FP)
        self.assertEqual(cal["canaries"], FAKE_CANARIES)
        # g = 0.5 * 40.0 = 20.0, k = 4.0 * 40.0 = 160.0
        self.assertAlmostEqual(cal["anchors"]["init.fresh-repo"]["L"]["g"], 20.0)
        self.assertAlmostEqual(cal["anchors"]["init.fresh-repo"]["L"]["k"], 160.0)
        self.assertEqual(cal["eps"]["INIT"]["L"], 2.0)

        record = json.loads(raw_baseline.decode("utf-8"))
        schema = baseline.load_schema()
        self.assertEqual(baseline.validate_against_schema(record, schema), [])

        # Plan section 5 V4: seven required negative fixtures must all fail.
        bad_cases: list[tuple[str, dict]] = []

        c1 = copy.deepcopy(record)
        c1["history"] = []
        bad_cases.append(("extra top-level history array", c1))

        c2 = copy.deepcopy(record)
        c2["categories"]["INIT"]["L"] = 100.5
        bad_cases.append(("category score 100.5", c2))

        c3 = copy.deepcopy(record)
        del c3["categories"]["SUITE"]
        bad_cases.append(("missing SUITE", c3))

        c4 = copy.deepcopy(record)
        del c4["categories"]["SUITE"]["IO"]
        bad_cases.append(("SUITE missing IO", c4))

        c5 = copy.deepcopy(record)
        c5["categories"]["FOO"] = {"L": 50.0, "U": 50.0, "M": 50.0, "IO": 50.0}
        bad_cases.append(("extra group FOO", c5))

        c6 = copy.deepcopy(record)
        c6["commit"] = "deadbeef"
        bad_cases.append(("short commit", c6))

        c7 = copy.deepcopy(record)
        c7["schema_version"] = 2
        bad_cases.append(("schema_version 2", c7))

        # Extra boundary checks: newline-smuggled commit, bool schema_version, negative score.
        c8 = copy.deepcopy(record)
        c8["commit"] = record["commit"] + "\n"
        bad_cases.append(("commit with trailing newline", c8))

        c9 = copy.deepcopy(record)
        c9["schema_version"] = True
        bad_cases.append(("bool schema_version", c9))

        for name, bad in bad_cases:
            with self.subTest(case=name):
                errs = baseline.validate_against_schema(bad, schema)
                self.assertTrue(errs, f"expected schema rejection for {name}")

    def test_init_picks_lower_composite_and_rejects_b_regression(self):
        code, _, err = self._run_main(["calibrate", "--runs", "4", "--src", str(self.src_dir)])
        self.assertEqual(code, 0, err)

        # Case 1: Run A slightly slower (lower composite), Run B slightly faster (within noise, no regression).
        # Must pick Run A.
        seq = iter([
            _make_samples(group_scale={"INIT": 1.02}),
            _make_samples(group_scale={"INIT": 0.99}),
        ])
        code, out, err = self._run_main(["init", "--src", str(self.src_dir)], measure=lambda s, g, r, **kw: next(seq))
        self.assertEqual(code, 0, err)
        self.assertIn("chosen=A", out)
        base_a = json.loads(baseline.baseline_path(self.state_dir).read_text(encoding="utf-8"))

        # Case 2: Run B slightly slower (lower composite, still within eps of A). Must pick Run B.
        seq2 = iter([
            _make_samples(group_scale={"INIT": 0.99}),
            _make_samples(group_scale={"INIT": 1.02}),
        ])
        code, out, err = self._run_main(["init", "--src", str(self.src_dir)], measure=lambda s, g, r, **kw: next(seq2))
        self.assertEqual(code, 0, err)
        self.assertIn("chosen=B", out)
        base_b = json.loads(baseline.baseline_path(self.state_dir).read_text(encoding="utf-8"))
        self.assertAlmostEqual(base_a["composite"], base_b["composite"], places=9)

        # Case 3: Run B regresses strongly against Run A -> exit 1, baseline file not overwritten.
        before = baseline.baseline_path(self.state_dir).read_bytes()
        seq3 = iter([
            _make_samples(),
            _make_samples(overrides={"init.fresh-repo": {"wall_ms": [80.0] * 200}}),
        ])
        code, _, _ = self._run_main(["init", "--src", str(self.src_dir)], measure=lambda s, g, r, **kw: next(seq3))
        self.assertEqual(code, 1)
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

    def test_calibrate_rejects_too_tight_eps_and_writes_no_file(self):
        normal = _make_samples()
        noisy = _make_samples(overrides={"init.fresh-repo": {"wall_ms": [60.0] * 200}})
        runs = iter([normal] * 7 + [noisy])

        code, _, err = self._run_main(
            ["calibrate", "--runs", "8", "--src", str(self.src_dir)],
            measure=lambda s, g, r, **kw: next(runs),
        )
        self.assertEqual(code, 2)
        self.assertIn("calibration noise fence too tight", err)
        self.assertFalse(baseline.calibration_path(self.state_dir).exists())

    def test_regression_while_composite_rises_exits_1(self):
        before = self._calibrate_and_init()
        base = json.loads(before.decode("utf-8"))

        # HOOK_HOT (weight 0.35) speeds up 1.8x -> big composite gain;
        # INIT.L (weight 0.02) slows down 2x -> regresses.
        samples = _make_samples(
            group_scale={"HOOK_HOT": 0.55},
            overrides={"init.fresh-repo": {"wall_ms": [80.0] * 200}},
        )
        code, out, _ = self._run_main(
            ["run", "--src", str(self.src_dir)],
            measure=lambda s, g, r, **kw: samples,
        )
        self.assertEqual(code, 1)
        self.assertIn("result: REGRESSION", out)
        self.assertIn("INIT.L", out)
        report = self._latest_report()
        self.assertGreater(report["composite"], base["composite"])
        self.assertEqual([r["category"] for r in report["regressed"]], ["INIT.L"])
        self.assertEqual(report["raised"], [])
        self.assertFalse(report["baseline_updated"])
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

    def test_overwrite_edges_exact_bar_and_lucky_point(self):
        before = self._calibrate_and_init()
        base = json.loads(before.decode("utf-8"))
        cal = json.loads(baseline.calibration_path(self.state_dir).read_text(encoding="utf-8"))
        h_init = base["categories"]["INIT"]["L"]
        eps_init = cal["eps"]["INIT"]["L"]
        g_val = cal["anchors"]["init.fresh-repo"]["L"]["g"]
        k_val = cal["anchors"]["init.fresh-repo"]["L"]["k"]

        # Exact value v such that subscore(v, g, k) == h_init + eps_init.
        target_score = h_init + eps_init
        v_exact = k_val / ((k_val / g_val) ** (target_score / 100.0))
        # Verify our constructed v_exact hits the exact boundary (clamp float rounding slightly below if needed).
        if scoring.subscore(v_exact, g_val, k_val) > target_score:
            v_exact = math.nextafter(v_exact, math.inf)
        self.assertLessEqual(scoring.subscore(v_exact, g_val, k_val), target_score)

        # Edge 1: C_pes == H + eps -> must NOT raise.
        samples_exact = _make_samples(overrides={"init.fresh-repo": {"wall_ms": [v_exact] * 200}})
        code, _, err = self._run_main(
            ["run", "--src", str(self.src_dir)],
            measure=lambda s, g, r, **kw: samples_exact,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

        # Edge 2: Lucky point clears H + eps, but pes (x_197) is slower and below H + eps -> must NOT raise.
        # 196 fast samples (25 ms -> score ~89.3), 4 slower samples at 40 ms -> x_197 = 40 ms (score 66.67 <= H+eps),
        # while p95 is between x_190 and x_191 (25 ms -> point ~89.3 > H+eps).
        lucky_wall = [25.0] * 196 + [40.0] * 4
        samples_lucky = _make_samples(overrides={"init.fresh-repo": {"wall_ms": lucky_wall}})
        code, _, err = self._run_main(
            ["run", "--src", str(self.src_dir)],
            measure=lambda s, g, r, **kw: samples_lucky,
        )
        self.assertEqual(code, 0, err)
        report = self._latest_report()
        self.assertGreater(report["categories"]["INIT.L"]["point"], h_init + eps_init)
        self.assertLessEqual(report["categories"]["INIT.L"]["pes"], h_init + eps_init)
        self.assertFalse(report["baseline_updated"])
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

        # Edge 3: Genuine improvement with --no-update leaves baseline byte-identical.
        samples_fast = _make_samples(overrides={"init.fresh-repo": {"wall_ms": [25.0] * 200}})
        code, _, err = self._run_main(
            ["run", "--no-update", "--src", str(self.src_dir)],
            measure=lambda s, g, r, **kw: samples_fast,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

    def test_one_raise_leaves_others_byte_identical_and_never_lowers(self):
        before = self._calibrate_and_init()
        base_before = json.loads(before.decode("utf-8"))

        # INIT.L improves strongly; ASSETS.L dips slightly (within noise floor, not a regression).
        # Only INIT.L should raise; ASSETS.L and all other 30 marks must stay identical.
        samples = _make_samples(
            overrides={
                "init.fresh-repo": {"wall_ms": [25.0] * 200},
                "assets.list-playbooks": {"wall_ms": [41.0] * 200},
            }
        )
        code, out, err = self._run_main(
            ["run", "--src", str(self.src_dir)],
            measure=lambda s, g, r, **kw: samples,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("baseline: updated", out)
        self.assertIn("raised: INIT.L", out)

        after_text = baseline.baseline_path(self.state_dir).read_text(encoding="utf-8")
        base_after = json.loads(after_text)
        self.assertGreater(base_after["categories"]["INIT"]["L"], base_before["categories"]["INIT"]["L"] + 2.0)

        for g in scoring.GROUPS:
            for m in scoring.METRICS:
                if (g, m) == ("INIT", "L"):
                    continue
                self.assertEqual(
                    json.dumps(base_after["categories"][g][m]),
                    json.dumps(base_before["categories"][g][m]),
                    f"mark {g}.{m} changed unexpectedly",
                )

        # No leftover .tmp files in state_dir.
        leftovers = [p.name for p in self.state_dir.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_error_gate_drops_category_to_zero_and_exits_1(self):
        before = self._calibrate_and_init()

        for fail_field in ("exit_ok", "digest_ok"):
            with self.subTest(fail_field=fail_field):
                samples = _make_samples(overrides={"init.fresh-repo": {fail_field: False}})
                code, out, _ = self._run_main(
                    ["run", "--src", str(self.src_dir)],
                    measure=lambda s, g, r, **kw: samples,
                )
                self.assertEqual(code, 1)
                self.assertIn("error gate", out)
                report = self._latest_report()
                for m in scoring.METRICS:
                    self.assertEqual(report["categories"][f"INIT.{m}"]["point"], 0.0)
                    self.assertEqual(report["categories"][f"INIT.{m}"]["opt"], 0.0)
                    self.assertEqual(report["categories"][f"INIT.{m}"]["pes"], 0.0)
                    self.assertTrue(report["categories"][f"INIT.{m}"]["error_failed"])
                self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

    def test_dilution_one_of_eight_hook_hot_slowed_15_percent(self):
        before = self._calibrate_and_init()
        # 7 of 8 HOOK_HOT benchmarks unchanged; 1 benchmark slowed by 15% (40.0 -> 46.0 ms).
        samples = _make_samples(overrides={"pre.pending.4m": {"wall_ms": [46.0] * 200}})
        code, out, _ = self._run_main(
            ["run", "--src", str(self.src_dir)],
            measure=lambda s, g, r, **kw: samples,
        )
        self.assertEqual(code, 1)
        self.assertIn("HOOK_HOT.L", out)
        report = self._latest_report()
        self.assertEqual([r["category"] for r in report["regressed"]], ["HOOK_HOT.L"])
        self.assertEqual(report["categories"]["HOOK_HOT.L"]["worst_benchmark"], "pre.pending.4m")
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

    def test_partial_runs_only_and_quick(self):
        before = self._calibrate_and_init()
        base_before = json.loads(before.decode("utf-8"))

        # Unknown selector -> exit 2, baseline byte-identical.
        code, _, err = self._run_main(["run", "--only", "NOPE", "--src", str(self.src_dir)])
        self.assertEqual(code, 2)
        self.assertIn("invalid --only selector", err)
        self.assertNotIn("NOPE", err)
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

        # --only and --quick together -> exit 2.
        code, _, _ = self._run_main(["run", "--only", "INIT", "--quick", "--src", str(self.src_dir)])
        self.assertEqual(code, 2)

        # Unselected group regresses (INIT slowed), but --only ASSETS passes and reports INIT.* as not measured.
        seen_groups: list[tuple[str, ...]] = []

        def measure_recording(src, groups, rdir, **kw):
            seen_groups.append(tuple(groups))
            return _make_samples(groups, overrides={"init.fresh-repo": {"wall_ms": [90.0] * 200}})

        code, out, err = self._run_main(
            ["run", "--only", "ASSETS", "--src", str(self.src_dir)],
            measure=measure_recording,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(seen_groups[-1], ("ASSETS",))
        self.assertIn("not measured:", out)
        self.assertIn("INIT.L", out)
        report = self._latest_report()
        self.assertTrue(report["partial"])
        self.assertEqual(report["categories"]["INIT.L"]["status"], "not measured")
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

        # Now selecting INIT on the same slowed sample MUST regress -> exit 1, baseline unchanged.
        code, out, _ = self._run_main(
            ["run", "--only", "INIT", "--src", str(self.src_dir)],
            measure=measure_recording,
        )
        self.assertEqual(code, 1)
        self.assertIn("INIT.L", out)
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

        # --quick selects every group except SUITE (on clean samples -> exit 0).
        seen_groups.clear()

        def measure_clean(src, groups, rdir, **kw):
            seen_groups.append(tuple(groups))
            return _make_samples(groups)

        code, _, err = self._run_main(
            ["run", "--quick", "--no-update", "--src", str(self.src_dir)],
            measure=measure_clean,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(seen_groups[-1], tuple(g for g in scoring.GROUPS if g != "SUITE"))
        report_q = self._latest_report()
        self.assertTrue(report_q["partial"])
        for m in scoring.METRICS:
            self.assertEqual(report_q["categories"][f"SUITE.{m}"]["status"], "not measured")

        # Partial raise on mixed selector (ASSETS,INIT.L):
        # Both INIT.L and INIT.U speed up, but only INIT.L is selected -> ONLY INIT.L is raised!
        samples_partial = _make_samples(
            ("ASSETS", "INIT"),
            overrides={"init.fresh-repo": {"wall_ms": [25.0] * 200, "cpu_ms": [20.0] * 200}},
        )
        code, out, err = self._run_main(
            ["run", "--only", "INIT.L,ASSETS", "--src", str(self.src_dir)],
            measure=lambda s, g, r, **kw: samples_partial,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("raised: INIT.L", out)
        base_after = json.loads(baseline.baseline_path(self.state_dir).read_text(encoding="utf-8"))
        self.assertGreater(base_after["categories"]["INIT"]["L"], base_before["categories"]["INIT"]["L"] + 2.0)
        # INIT.U was NOT selected, so it must stay identical!
        self.assertEqual(base_after["categories"]["INIT"]["U"], base_before["categories"]["INIT"]["U"])
        for g in scoring.GROUPS:
            for m in scoring.METRICS:
                if (g, m) == ("INIT", "L"):
                    continue
                self.assertEqual(
                    json.dumps(base_after["categories"][g][m]),
                    json.dumps(base_before["categories"][g][m]),
                )

    def test_exit_2_gates_leave_baseline_byte_identical(self):
        before = self._calibrate_and_init()

        # 1. Host fingerprint mismatch.
        code, _, err = self._run_main(
            ["run", "--src", str(self.src_dir)],
            fingerprint=lambda: "f" * 64,
        )
        self.assertEqual(code, 2)
        self.assertIn("host fingerprint mismatch", err)
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

        # 2. Canary p50 off by > 10%.
        drifted = dict(FAKE_CANARIES)
        drifted["python_startup_p50_ms"] = FAKE_CANARIES["python_startup_p50_ms"] * 1.15
        code, _, err = self._run_main(
            ["run", "--src", str(self.src_dir)],
            canaries=lambda rdir: drifted,
        )
        self.assertEqual(code, 2)
        self.assertIn("host canary drift above limit", err)
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

        # 3. 1-minute loadavg > 1.0.
        code, _, err = self._run_main(
            ["run", "--src", str(self.src_dir)],
            loadavg=lambda: 1.25,
        )
        self.assertEqual(code, 2)
        self.assertIn("host load average above limit", err)
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

        # 4. fixtures_sha256 mismatch.
        code, _, err = self._run_main(
            ["run", "--src", str(self.src_dir)],
            build_fixtures=lambda root: "e" * 64,
        )
        self.assertEqual(code, 2)
        self.assertIn("baseline fixtures mismatch", err)
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

        # 5. HarnessError raised during measurement.
        def boom(src, groups, rdir, **kw):
            raise HarnessError("missing ru binary")

        code, _, err = self._run_main(["run", "--src", str(self.src_dir)], measure=boom)
        self.assertEqual(code, 2)
        self.assertIn("measurement harness failure", err)
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)

        # 6. calibration_sha256 mismatch (modify calibration.json bytes).
        cal_path = baseline.calibration_path(self.state_dir)
        cal_before = cal_path.read_bytes()
        cal_obj = json.loads(cal_before.decode("utf-8"))
        cal_obj["runs"] = 99
        cal_path.write_text(json.dumps(cal_obj, indent=2) + "\n", encoding="utf-8")
        code, _, err = self._run_main(["run", "--src", str(self.src_dir)])
        self.assertEqual(code, 2)
        self.assertIn("baseline calibration mismatch", err)
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), before)
        cal_path.write_bytes(cal_before)

        # 7. config_sha256 mismatch (baseline holds different config_sha256).
        base_obj = json.loads(before.decode("utf-8"))
        base_obj["config_sha256"] = "0" * 64
        baseline.save_baseline(self.state_dir, base_obj)
        tampered = baseline.baseline_path(self.state_dir).read_bytes()
        code, _, err = self._run_main(["run", "--src", str(self.src_dir)])
        self.assertEqual(code, 2)
        self.assertIn("baseline config mismatch", err)
        self.assertEqual(baseline.baseline_path(self.state_dir).read_bytes(), tampered)

    def test_run_dir_pruning_default_git_archive_and_no_path_leak(self):
        self._calibrate_and_init()
        captured_srcs: list[Path] = []

        def inspect_src(src, groups, rdir, **kw):
            captured_srcs.append(src)
            self.assertTrue((src / "hooks" / "handoff-guard.py").is_file())
            return _make_samples(groups)

        # Run without --src so git archive HEAD plugins/byte-stack is unpacked under run_dir.
        for _ in range(4):
            code, out, err = self._run_main(
                ["run", "--only", "INIT", "--no-update"],
                measure=inspect_src,
            )
            self.assertEqual(code, 0, err)
            # Fixed text + numbers only: never leak XDG_STATE_HOME or temp paths.
            self.assertNotIn(str(self.temp), out)
            self.assertNotIn(str(self.temp), err)
            self.assertNotIn("xdg-state-secret-marker", out)
            self.assertNotIn("xdg-state-secret-marker", err)

        self.assertEqual(len(captured_srcs), 4)
        # Keep only newest 3 run folders.
        run_dirs = [p for p in (self.state_dir / "runs").iterdir() if p.is_dir()]
        self.assertEqual(len(run_dirs), 3)

        # Hostile CLI arguments must never be echoed in error output (CODING_STANDARDS.md).
        hostile = "/example/secret-user/private\n;rm -rf /"
        for argv in (
            ["run", "--only", hostile],
            ["run", "--src", hostile],
            ["run", "--unknown-flag=" + hostile],
        ):
            code, out, err = self._run_main(argv)
            self.assertEqual(code, 2)
            self.assertNotIn("secret-user", out + err)
            self.assertNotIn("private", out + err)


if __name__ == "__main__":
    unittest.main()
