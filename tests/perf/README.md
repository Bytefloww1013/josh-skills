# byte-stack performance scan

The scan times every byte-stack entrypoint on fixed fixtures. It scores each component against its best verified result so far, and exits 1 when a category gets measurably worse. It lives under `tests/`, so none of it ships with the plugin. Issue #36 has the full design.

## Requirements

- Linux: the scan reads `/proc/self/io`.
- `cc`.
- Python 3.9 or later.
- `hyperfine` 1.19.0 on `PATH`. Install the release binary `hyperfine-v1.19.0-x86_64-unknown-linux-musl.tar.gz` from the sharkdp/hyperfine GitHub releases (SHA-256 `825287143f397774093539ca2458854ab3735c0e8a1aaf075c22edce7d261556`), or run `cargo install hyperfine --version 1.19.0 --locked`.
- `uvx`, only for the schema check in `verify_scan.sh`.

Run scans on an idle host. The scan waits up to `load_wait_s` (180 s) for the 1-minute load average to fall to `max_loadavg_1m` (1.0), then exits 2.

## Commands

Run every command from the repository root.

| Command | What it does | Time |
| --- | --- | --- |
| `python3 tests/perf/scan.py calibrate --runs 8` | Runs 8 identical scans and writes this host's anchors, noise floors and canary values to `calibration.json`. | about 95 min |
| `python3 tests/perf/scan.py init` | Runs two scans, A and B. If B shows no regression against A, writes the one with the lower composite score as `baseline.json`. Exits 2 if `baseline.json` already exists. | about 25 min |
| `python3 tests/perf/scan.py init --reset` | Deliberately replaces an existing `baseline.json` after the same A/B check and lower-composite pick. | about 25 min |
| `python3 tests/perf/scan.py run` | Measures, scores, compares with the baseline, and raises any mark that improved beyond the noise floor. | about 12 min |
| `python3 tests/perf/scan.py run --only ASSETS,INIT.L` | Measures and judges only those categories. Every other category is reported as `not measured` and its mark stays as it is. | seconds to minutes |
| `python3 tests/perf/scan.py run --quick` | The same as `--only` with every group but `SUITE`. | about 6 min |
| `python3 tests/perf/scan.py run --no-update --src DIR` | Compares a different plugin tree and never writes the baseline. | about 12 min |
| `bash tests/perf/verify_scan.sh` | Runs the external checks V1–V6 in a throwaway state folder. It needs a calibration first. | about 1h30 |

By default the scan measures `git archive HEAD plugins/byte-stack`, so uncommitted edits are not measured. Use `--src` to measure them.

## Exit codes

- **0:** pass. The baseline may have been raised.
- **1:** at least one category regressed. This holds even if the composite score rose.
- **2:** a harness, fixture or environment error. Examples: a missing tool, a wrong sample count, a host or calibration mismatch, a busy host, or an unknown `--only` selector.

Exit 1 or 2 never writes the baseline.

## Categories and scores

A category is one of 8 groups crossed with one of 4 metrics: `HOOK_HOT`, `HOOK_LIFECYCLE`, `ASSETS`, `BRIEFS`, `CAPTURE`, `EXTRACT`, `INIT`, `SUITE` × `L` (p95 wall time), `U` (p95 CPU time), `M` (p95 peak RSS), `IO` (median `rchar + wchar`). `benchmarks.py` lists each group's benchmarks.

- **Sub-score:** each benchmark and metric scores `s(v) = 100 · clamp(ln(k/v) / ln(k/g), 0, 1)`. The anchors are `g = 0.5 × p50` and `k = 4 × p95`, taken from calibration.
- **Category score:** the worst benchmark in its group. A wrong exit code or a changed stdout digest sets it to 0.
- **Regression:** a category regresses when its optimistic score is below its mark by more than its noise floor `ε`. The optimistic score comes from the lower bound of the p95 confidence interval.
- **Raise:** a mark is raised only when the pessimistic score clears it by more than `ε`. The pessimistic score comes from the upper bound of that interval. Marks never go down.
- **Noise floor:** `ε = max(2.0, 1.5 × IQR)` of the category's scores across the calibration scans.

`config.json` holds the weights, sample counts and thresholds.

## Files and state

All state is local to this host, in `$XDG_STATE_HOME/byte-stack-perf/` (default `~/.local/state/byte-stack-perf/`):

- `calibration.json`: the anchors, noise floors, canary values and host fingerprint.
- `baseline.json`: one high-water mark per category and no history. It validates against `baseline.schema.json`.
- `.lock`: exclusive non-blocking lock held while a scan runs; a concurrent scan in the same state folder exits 2.
- `runs/<utc>/`: the newest 3 runs' raw samples and `report.json`.

The host fingerprint is a SHA-256 of the CPU model, core count, CPU governor, kernel major version and the Python and hyperfine versions. If any of them changes, the scan exits 2 until you run `calibrate` and `init` again.

The scan never reads or writes `~/.claude`. Each hook benchmark gets a throwaway `HOME` and a synthetic transcript.

## Tests

`python3 -m unittest tests/test_byte_stack_perf.py tests/test_byte_stack_perf_sampler.py` covers the scoring rules on synthetic samples and the measurement layer on small runs. It takes a few seconds.
