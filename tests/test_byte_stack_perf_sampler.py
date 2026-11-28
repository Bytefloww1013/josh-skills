"""Unit tests for the byte-stack performance scan measurement layer (slice A)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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

    def test_warmup_nonzero_exit_fails_exit_ok(self):
        plugin = fixtures.unpack_head_archive(self.tmp / "plugin-warmup")
        script = plugin / "skills" / "init" / "scripts" / "init.py"
        body = script.read_text(encoding="utf-8")
        idx = body.index("\n")
        marker = self.tmp / "warmup-once-marker"
        injected = (
            "\nimport os\nfrom pathlib import Path\n"
            f"_m = Path({str(marker)!r})\n"
            'if "PERF_RU_OUT" in os.environ and not _m.exists():\n'
            "    _m.write_text('1', encoding='utf-8')\n"
            "    raise SystemExit(17)\n"
        )
        script.write_text(body[:idx] + injected + body[idx:], encoding="utf-8")

        result = sampler.measure(
            plugin,
            ["INIT"],
            self.tmp / "run-warmup-fail",
            rounds=1,
            warmup=1,
            _sample_counts={"INIT": 2},
        )
        entry = result["init.fresh-repo"]
        self.assertFalse(entry["exit_ok"])
        self.assertEqual(len(entry["wall_ms"]), 2)
        self.assertEqual(len(entry["cpu_ms"]), 2)
        self.assertEqual(len(entry["rss_kb"]), 2)
        self.assertEqual(len(entry["io_bytes"]), 2)

    def test_canary_nonzero_exit_raises_harness_error(self):
        tools = self.tmp / "fake-tools"
        tools.mkdir()
        false_exe = shutil.which("false")
        self.assertIsNotNone(false_exe)
        (tools / "true").symlink_to(false_exe)
        with mock.patch.dict(os.environ, {"PATH": str(tools) + os.pathsep + os.environ["PATH"]}):
            with mock.patch.multiple(sampler, _CANARY_RUNS=2, _CANARY_WARMUP=1, _taskset_prefix=lambda: []):
                with self.assertRaises(sampler.HarnessError):
                    sampler.canaries(self.tmp / "bad-canary")

    def test_ru_exec_failure_raises_harness_error_while_real_exit_127_is_measured(self):
        ru = sampler.build_ru(self.tmp / "bin-exec")
        ru_out = self.tmp / "exec-fail.ru"
        ru_out.write_bytes(b"")
        proc = subprocess.run(
            ["sh", "-c", 'exec "$@" 3>>"$PERF_RU_OUT"', "sh", str(ru), "nonexistent-perf-cmd-xyz"],
            env={**os.environ, "PERF_RU_OUT": str(ru_out)},
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 125)
        self.assertEqual(ru_out.read_text(encoding="utf-8").strip(), "EXEC_FAIL")

        hf = shutil.which("hyperfine")
        self.assertIsNotNone(hf)
        with self.assertRaises(sampler.HarnessError) as ctx:
            sampler._run_hyperfine_round(
                hf,
                [],
                ru,
                ("nonexistent-perf-cmd-xyz",),
                cwd=self.tmp,
                env=os.environ,
                runs=2,
                warmup=1,
                json_out=self.tmp / "exec-fail.json",
                ru_out=self.tmp / "exec-fail-hf.ru",
            )
        self.assertEqual(str(ctx.exception), "benchmark command could not start")

        # A launched child that genuinely exits 127 must remain a normal measured row.
        wall_ms, rows, all_exits = sampler._run_hyperfine_round(
            hf,
            [],
            ru,
            ("/bin/sh", "-c", "exit 127"),
            cwd=self.tmp,
            env=os.environ,
            runs=2,
            warmup=1,
            json_out=self.tmp / "real-127.json",
            ru_out=self.tmp / "real-127.ru",
        )
        self.assertEqual(len(wall_ms), 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(all_exits, [127, 127, 127])

    def test_materialize_is_independent_of_candidate_capture_writer_and_group_scoped(self):
        fx_dir = self.tmp / "fx-f7"
        fixtures.build(fx_dir)
        captured = fx_dir / "capture-repo" / ".byte-stack" / "playbooks" / "perf-fixture.md"
        self.assertTrue(captured.is_file())

        # Per-group materialization only sets up selected groups.
        work_init = self.tmp / "work-init-only"
        fixtures.materialize(fx_dir, work_init, ["INIT"])
        self.assertTrue((work_init / "init-repo" / ".git").is_dir())
        self.assertFalse((work_init / "extract-repo").exists())
        self.assertFalse((work_init / "capture-repo").exists())
        self.assertFalse((work_init / "proj-override").exists())
        self.assertFalse((work_init / "transcripts").exists())

        # Breaking capture_playbook.py write must not break an INIT scan, and during CAPTURE
        # it must fail capture.write-dry-run via exit_ok rather than crashing materialize().
        plugin = fixtures.unpack_head_archive(self.tmp / "plugin-broken-capture")
        cap_script = plugin / "skills" / "bmode" / "scripts" / "capture_playbook.py"
        body = cap_script.read_text(encoding="utf-8")
        first_nl = body.index("\n")
        second_nl = body.index("\n", first_nl + 1)
        cap_script.write_text(
            body[:second_nl]
            + "\nimport sys\nif len(sys.argv) > 1 and sys.argv[1] == 'write':\n    raise SystemExit(17)\n"
            + body[second_nl:],
            encoding="utf-8",
        )

        init_res = sampler.measure(
            plugin,
            ["INIT"],
            self.tmp / "run-init-broken-cap",
            rounds=1,
            warmup=1,
            _sample_counts={"INIT": 2},
        )
        self.assertTrue(init_res["init.fresh-repo"]["exit_ok"])
        self.assertTrue(init_res["init.fresh-repo"]["digest_ok"])

        cap_res = sampler.measure(
            plugin,
            ["CAPTURE"],
            self.tmp / "run-cap-broken-cap",
            rounds=1,
            warmup=1,
            _sample_counts={"CAPTURE": 2},
        )
        self.assertTrue(cap_res["capture.validate"]["exit_ok"])
        self.assertTrue(cap_res["capture.validate"]["digest_ok"])
        self.assertFalse(cap_res["capture.write-dry-run"]["exit_ok"])

    def test_ru_excludes_own_snapshot_io_and_measures_child_reads(self):
        ru = sampler.build_ru(self.tmp / "bin-io")

        # Static child that reads its own /proc/self/io once, prints it, and exits immediately.
        # Its true kernel-accounted I/O is (rchar at entry + bytes read from /proc/self/io)
        # and (syscr at entry + 1). ru must not inflate those with its own snapshot read.
        self_io_src = self.tmp / "self_io.c"
        self_io_exe = self.tmp / "self_io"
        self_io_src.write_text(
            "#include <fcntl.h>\n"
            "#include <unistd.h>\n"
            "int main(void) {\n"
            '  char buf[4096];\n'
            '  int fd = open("/proc/self/io", O_RDONLY);\n'
            "  ssize_t n = read(fd, buf, sizeof(buf));\n"
            "  if (n > 0) {\n"
            "    ssize_t w = write(1, buf, (size_t)n);\n"
            "    (void)w;\n"
            "  }\n"
            "  _exit(0);\n"
            "}\n",
            encoding="utf-8",
        )
        subprocess.run(["cc", "-O2", "-static", "-o", str(self_io_exe), str(self_io_src)], check=True)

        ru_out = self.tmp / "self-io.ru"
        ru_out.write_bytes(b"")
        proc = subprocess.run(
            ["sh", "-c", 'exec "$@" 3>>"$PERF_RU_OUT"', "sh", str(ru), str(self_io_exe)],
            env={**os.environ, "PERF_RU_OUT": str(ru_out)},
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0)
        child_io_bytes = proc.stdout
        child_io = {}
        for line in child_io_bytes.decode("utf-8").splitlines():
            k, v = line.split(":", 1)
            child_io[k.strip()] = int(v.strip())
        expected_rchar = child_io["rchar"] + len(child_io_bytes)
        expected_syscr = child_io["syscr"] + 1

        fields = [int(tok) for tok in ru_out.read_text(encoding="utf-8").strip().split()]
        self.assertEqual(len(fields), 7)
        _, _, _, ru_rchar, _, ru_syscr, rc = fields
        self.assertEqual(rc, 0)
        self.assertEqual(ru_rchar, expected_rchar)
        self.assertEqual(ru_syscr, expected_syscr)

        # Static child that reads a known N-byte file reports rchar >= N (and delta >= N).
        reader_src = self.tmp / "reader.c"
        reader_exe = self.tmp / "reader"
        reader_src.write_text(
            "#include <fcntl.h>\n"
            "#include <unistd.h>\n"
            "int main(int argc, char **argv) {\n"
            "  if (argc < 2) _exit(2);\n"
            "  int fd = open(argv[1], O_RDONLY);\n"
            "  char buf[4096];\n"
            "  while (read(fd, buf, sizeof(buf)) > 0) {}\n"
            "  _exit(0);\n"
            "}\n",
            encoding="utf-8",
        )
        subprocess.run(["cc", "-O2", "-static", "-o", str(reader_exe), str(reader_src)], check=True)
        payload = self.tmp / "known-read.bin"
        payload.write_bytes(b"z" * 32768)
        ru_out2 = self.tmp / "reader.ru"
        ru_out2.write_bytes(b"")
        proc2 = subprocess.run(
            ["sh", "-c", 'exec "$@" 3>>"$PERF_RU_OUT"', "sh", str(ru), str(reader_exe), str(payload)],
            env={**os.environ, "PERF_RU_OUT": str(ru_out2)},
            capture_output=True,
        )
        self.assertEqual(proc2.returncode, 0)
        _, _, _, read_rchar, _, _, read_rc = [
            int(tok) for tok in ru_out2.read_text(encoding="utf-8").strip().split()
        ]
        self.assertEqual(read_rc, 0)
        self.assertGreaterEqual(read_rchar, 32768)

    def test_malformed_inputs_and_subprocess_timeouts_raise_fixed_text_harness_error(self):
        # 1. Malformed ru output rows (invalid UTF-8, bad token, negative counter, wrong field count).
        bad_utf8 = self.tmp / "bad-utf8.ru"
        bad_utf8.write_bytes(b"\xff\xfe\n")
        with self.assertRaises(sampler.HarnessError):
            sampler._parse_ru_lines(bad_utf8, 1)

        secret_tok = "SECRET_RU_TOKEN_99"
        for content in (
            f"0 0 100 {secret_tok} 0 1 0\n",
            "0 0 100 -1 0 1 0\n",
            "0 0 100 10 0 1\n",
        ):
            p = self.tmp / "bad.ru"
            p.write_text(content, encoding="utf-8")
            with self.assertRaises(sampler.HarnessError) as ctx:
                sampler._parse_ru_lines(p, 1)
            self.assertNotIn(secret_tok, str(ctx.exception))

        # 2. Non-numeric hyperfine JSON samples raise fixed-text HarnessError, never ValueError/TypeError.
        ru = sampler.build_ru(self.tmp / "bin-f4")
        hf = shutil.which("hyperfine")
        self.assertIsNotNone(hf)
        for bad_sample in ("SECRET_SAMPLE_STR", None, True, -0.5):
            json_out = self.tmp / "hf-bad.json"
            ru_out = self.tmp / "hf-bad.ru"

            def fake_hf_run(*args, **kwargs):
                json_out.write_text(json.dumps({"results": [{"times": [bad_sample]}]}), encoding="utf-8")
                ru_out.write_text("0 0 100 0 0 0 0\n", encoding="utf-8")
                return subprocess.CompletedProcess(args[0], 0, "", "")

            with mock.patch.object(sampler.subprocess, "run", side_effect=fake_hf_run):
                with self.assertRaises(sampler.HarnessError) as ctx:
                    sampler._run_hyperfine_round(
                        hf,
                        [],
                        ru,
                        ("true",),
                        cwd=self.tmp,
                        env=os.environ,
                        runs=1,
                        warmup=0,
                        json_out=json_out,
                        ru_out=ru_out,
                    )
            self.assertNotIn("SECRET_SAMPLE_STR", str(ctx.exception))

        # 3. Subprocess timeouts in fixtures and sampler raise fixed-text HarnessError.
        secret_cmd = ["/secret/host/path/cmd"]
        timeout_exc = subprocess.TimeoutExpired(cmd=secret_cmd, timeout=1)

        with mock.patch.object(fixtures.subprocess, "run", side_effect=timeout_exc):
            with self.assertRaises(fixtures.HarnessError) as ctx_git:
                fixtures._git_init_repo(self.tmp / "timeout-repo", self.tmp / "git-home")
            self.assertNotIn("/secret/host/path", str(ctx_git.exception))

            with self.assertRaises(fixtures.HarnessError) as ctx_arc:
                fixtures.unpack_head_archive(self.tmp / "timeout-arc")
            self.assertNotIn("/secret/host/path", str(ctx_arc.exception))

            spec_with_prep = benchmarks.BenchmarkSpec(
                name="test.prep",
                group="INIT",
                argv=("true",),
                cwd=self.tmp,
                env=os.environ,
                prepare_argv=("true",),
            )
            with self.assertRaises(fixtures.HarnessError) as ctx_prep:
                fixtures.run_spec_once(spec_with_prep, self.tmp, self.tmp)
            self.assertNotIn("/secret/host/path", str(ctx_prep.exception))

            spec_no_prep = benchmarks.BenchmarkSpec(
                name="test.run",
                group="INIT",
                argv=("true",),
                cwd=self.tmp,
                env=os.environ,
            )
            with self.assertRaises(fixtures.HarnessError) as ctx_run:
                fixtures.run_spec_once(spec_no_prep, self.tmp, self.tmp)
            self.assertNotIn("/secret/host/path", str(ctx_run.exception))

        with mock.patch.object(sampler.subprocess, "run", side_effect=timeout_exc):
            with self.assertRaises(sampler.HarnessError) as ctx_hf:
                sampler._run_hyperfine_round(
                    hf,
                    [],
                    ru,
                    ("true",),
                    cwd=self.tmp,
                    env=os.environ,
                    runs=1,
                    warmup=0,
                    json_out=self.tmp / "timeout.json",
                    ru_out=self.tmp / "timeout.ru",
                )
            self.assertNotIn("/secret/host/path", str(ctx_hf.exception))


if __name__ == "__main__":
    unittest.main()
