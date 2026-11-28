"""Unit tests for the byte-stack performance scan measurement layer (slice A)."""
from __future__ import annotations

import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PERF_DIR = ROOT / "tests" / "perf"
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

import benchmarks
import fingerprint
import fixtures
import sampler

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class PerfSamplerTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory(prefix="perf-sampler-test-")
        self.addCleanup(td.cleanup)
        self.tmp = Path(td.name)

    def test_contract_constants(self):
        self.assertEqual(
            benchmarks.GROUPS,
            ("HOOK_HOT", "HOOK_LIFECYCLE", "ASSETS", "BRIEFS", "CAPTURE", "EXTRACT", "INIT", "SUITE"),
        )
        self.assertEqual(benchmarks.METRICS, ("L", "U", "M", "IO"))
        self.assertEqual(set(sampler.SAMPLE_COUNTS.keys()), set(benchmarks.GROUPS))
        for group, n in sampler.SAMPLE_COUNTS.items():
            expected_n = 100 if group == "SUITE" else 200
            self.assertEqual(n, expected_n, group)
            self.assertEqual(n % 4, 0, group)

    def test_fixtures_build_byte_identical_twice(self):
        dir_a = self.tmp / "fx-a"
        dir_b = self.tmp / "fx-b"
        sha_a = fixtures.build(dir_a)
        sha_b = fixtures.build(dir_b)
        self.assertRegex(sha_a, HEX64_RE)
        self.assertEqual(sha_a, sha_b)

        files_a = sorted(p.relative_to(dir_a).as_posix() for p in dir_a.rglob("*") if p.is_file())
        files_b = sorted(p.relative_to(dir_b).as_posix() for p in dir_b.rglob("*") if p.is_file())
        self.assertEqual(files_a, files_b)

        extract_files = [f for f in files_a if f.startswith("extract-repo/")]
        self.assertEqual(len(extract_files), 300)

        host = socket.gethostname()
        home = str(Path.home())
        for rel in files_a:
            bytes_a = (dir_a / rel).read_bytes()
            bytes_b = (dir_b / rel).read_bytes()
            self.assertEqual(bytes_a, bytes_b, rel)
            self.assertNotIn(home.encode("utf-8"), bytes_a, rel)
            self.assertNotIn(str(dir_a).encode("utf-8"), bytes_a, rel)
            if len(host) >= 4:
                self.assertNotIn(host.encode("utf-8"), bytes_a, rel)

    def test_ru_reports_small_maxrss_and_nonzero_rchar(self):
        ru = sampler.build_ru(self.tmp / "bin")

        def run_ru(argv: list[str]) -> list[int]:
            ru_out = self.tmp / "ru.out"
            ru_out.write_bytes(b"")
            # Open fd 3 through a shell redirect, as sampler.py does (a preexec_fn dup2 is undone on Python 3.9).
            proc = subprocess.run(
                ["sh", "-c", 'exec "$@" 3>>"$PERF_RU_OUT"', "sh", str(ru), *argv],
                env={**os.environ, "PERF_RU_OUT": str(ru_out)},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", errors="replace"))
            lines = [line for line in ru_out.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(lines), 1)
            fields = [int(tok) for tok in lines[0].split()]
            self.assertEqual(len(fields), 7)
            return fields

        # true: small maxrss (< 4000 KB), exit 0
        utime_us, stime_us, maxrss_kb, rchar, wchar, syscr, rc = run_ru(["true"])
        self.assertGreaterEqual(utime_us, 0)
        self.assertGreaterEqual(stime_us, 0)
        self.assertGreater(maxrss_kb, 0)
        self.assertLess(maxrss_kb, 4000)
        self.assertGreaterEqual(rchar, 0)
        self.assertGreaterEqual(wchar, 0)
        self.assertGreaterEqual(syscr, 0)
        self.assertEqual(rc, 0)

        # cat of a file: non-zero rchar (note: uutils cat may use splice(2) for the payload itself).
        payload = self.tmp / "sample.bin"
        payload.write_bytes(b"a" * 65536)
        _, _, _, cat_rchar, _, cat_syscr, cat_rc = run_ru(["cat", str(payload)])
        self.assertGreater(cat_rchar, 0)
        self.assertGreater(cat_syscr, 0)
        self.assertEqual(cat_rc, 0)

        # Explicit userspace read() of the 64 KB file: rchar delta must cover the full file size.
        _, _, _, read_rchar, _, _, read_rc = run_ru(
            [sys.executable, "-I", "-c", "import sys; open(sys.argv[1], 'rb').read()", str(payload)]
        )
        self.assertGreaterEqual(read_rchar, 65536)
        self.assertEqual(read_rc, 0)

    def test_fingerprint_and_toolchain(self):
        old = os.environ.get("PERF_FINGERPRINT_OVERRIDE")
        try:
            os.environ.pop("PERF_FINGERPRINT_OVERRIDE", None)
            fp1 = fingerprint.fingerprint()
            fp2 = fingerprint.fingerprint()
            self.assertRegex(fp1, HEX64_RE)
            self.assertEqual(fp1, fp2)

            os.environ["PERF_FINGERPRINT_OVERRIDE"] = "synthetic-host-a"
            fp_a = fingerprint.fingerprint()
            os.environ["PERF_FINGERPRINT_OVERRIDE"] = "synthetic-host-b"
            fp_b = fingerprint.fingerprint()
            self.assertRegex(fp_a, HEX64_RE)
            self.assertRegex(fp_b, HEX64_RE)
            self.assertNotEqual(fp_a, fp_b)
            self.assertNotEqual(fp_a, fp1)
        finally:
            if old is None:
                os.environ.pop("PERF_FINGERPRINT_OVERRIDE", None)
            else:
                os.environ["PERF_FINGERPRINT_OVERRIDE"] = old

        ru = sampler.build_ru(self.tmp / "bin")
        tc = fingerprint.toolchain(ru)
        self.assertEqual(set(tc.keys()), {"python", "hyperfine", "ru_sha256"})
        self.assertRegex(tc["python"], r"^3\.\d+\.\d+$")
        self.assertRegex(tc["hyperfine"], r"^\d+\.\d+\.\d+$")
        self.assertRegex(tc["ru_sha256"], HEX64_RE)

    def test_measure_cheap_group_contract_shape(self):
        src = fixtures.unpack_head_archive(self.tmp / "archived")
        run_dir = self.tmp / "run"
        res = sampler.measure(
            src,
            ["INIT"],
            run_dir,
            rounds=2,
            warmup=1,
            _sample_counts={"INIT": 4},
        )
        self.assertEqual(set(res.keys()), {"init.fresh-repo"})
        entry = res["init.fresh-repo"]
        self.assertEqual(
            set(entry.keys()),
            {"group", "wall_ms", "cpu_ms", "rss_kb", "io_bytes", "exit_ok", "digest_ok"},
        )
        self.assertEqual(entry["group"], "INIT")
        self.assertEqual(len(entry["wall_ms"]), 4)
        self.assertEqual(len(entry["cpu_ms"]), 4)
        self.assertEqual(len(entry["rss_kb"]), 4)
        self.assertEqual(len(entry["io_bytes"]), 4)
        self.assertTrue(all(isinstance(v, float) and v > 0 for v in entry["wall_ms"]))
        self.assertTrue(all(isinstance(v, float) and v >= 0 for v in entry["cpu_ms"]))
        self.assertTrue(all(isinstance(v, int) and v > 0 for v in entry["rss_kb"]))
        self.assertTrue(all(isinstance(v, int) and v > 0 for v in entry["io_bytes"]))
        self.assertTrue(entry["exit_ok"])
        self.assertTrue(entry["digest_ok"])

    def test_canaries_contract_shape(self):
        res = sampler.canaries(self.tmp / "canary-run")
        self.assertEqual(set(res.keys()), {"ru_true_p50_ms", "python_startup_p50_ms"})
        self.assertIsInstance(res["ru_true_p50_ms"], float)
        self.assertIsInstance(res["python_startup_p50_ms"], float)
        self.assertGreater(res["ru_true_p50_ms"], 0.0)
        self.assertGreater(res["python_startup_p50_ms"], 0.0)

    def test_deleted_ru_binary_raises_harness_error(self):
        ru = sampler.build_ru(self.tmp / "bin")
        ru.unlink()
        old_ru = os.environ.get("RU")
        try:
            os.environ["RU"] = str(ru)
            with self.assertRaises(sampler.HarnessError) as ctx:
                sampler.build_ru(self.tmp / "bin2")
            self.assertNotIn(str(ru), str(ctx.exception))

            src = fixtures.unpack_head_archive(self.tmp / "archived")
            with self.assertRaises(sampler.HarnessError) as ctx2:
                sampler.measure(
                    src,
                    ["INIT"],
                    self.tmp / "run-missing-ru",
                    rounds=2,
                    warmup=1,
                    _sample_counts={"INIT": 2},
                )
            self.assertNotIn(str(ru), str(ctx2.exception))

            with self.assertRaises(sampler.HarnessError) as ctx3:
                fingerprint.toolchain(ru)
            self.assertNotIn(str(ru), str(ctx3.exception))
        finally:
            if old_ru is None:
                os.environ.pop("RU", None)
            else:
                os.environ["RU"] = old_ru

    def test_ru_line_count_mismatch_raises_harness_error(self):
        fake_ru = self.tmp / "fake-ru"
        fake_ru.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_ru.chmod(0o755)
        old_ru = os.environ.get("RU")
        try:
            os.environ["RU"] = str(fake_ru)
            src = fixtures.unpack_head_archive(self.tmp / "archived")
            with self.assertRaises(sampler.HarnessError) as ctx:
                sampler.measure(
                    src,
                    ["INIT"],
                    self.tmp / "run-bad-ru",
                    rounds=2,
                    warmup=1,
                    _sample_counts={"INIT": 2},
                )
            self.assertIn("line count", str(ctx.exception))
        finally:
            if old_ru is None:
                os.environ.pop("RU", None)
            else:
                os.environ["RU"] = old_ru

    def test_boundary_errors_use_fixed_text(self):
        src = fixtures.unpack_head_archive(self.tmp / "archived")
        sentinel = "UNEXPECTED_GROUP_VALUE_42"
        with self.assertRaises(sampler.HarnessError) as ctx:
            sampler.measure(src, [sentinel], self.tmp / "run-bad-group")
        self.assertNotIn(sentinel, str(ctx.exception))

        with self.assertRaises(sampler.HarnessError):
            sampler.measure(src, ["INIT"], self.tmp / "run-bad-div", rounds=3, _sample_counts={"INIT": 4})


if __name__ == "__main__":
    unittest.main()
