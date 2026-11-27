"""Run from any directory with python3 -I tests/test_byte_stack_extract.py."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "plugins/byte-stack/skills"


def make_playbook_candidate(
    key="release-notes.md",
    title="Release notes",
    use_when="Prepare release notes for a tagged version.",
    steps=None,
    verification=None,
    provenance=None,
    category="workflow",
    rationale="Automates the documented release procedure.",
):
    return {
        "id": f"playbooks/{key}",
        "category": category,
        "kind": "playbooks",
        "key": key,
        "provenance": provenance or [{"path": "Makefile", "command": "python3 -m unittest", "line": 4}],
        "rationale": rationale,
        "payload": {
            "title": title,
            "use_when": use_when,
            "steps": steps or ["Run python3 -m unittest across the suite", "Tag the verified release"],
            "verification": verification or ["Confirm all unit tests exit 0"],
        },
    }


def make_workflow_candidate(
    key="ci-preflight.md",
    title="CI preflight",
    steps=None,
    verification=None,
    provenance=None,
):
    return {
        "id": f"workflows/{key}",
        "category": "workflow",
        "kind": "workflows",
        "key": key,
        "provenance": provenance or [{"path": ".github/workflows/ci.yml", "command": "pytest -q"}],
        "payload": {
            "title": title,
            "steps": steps or ["Run pytest -q before pushing changes"],
            "verification": verification or ["All CI checks pass with exit 0"],
        },
    }


def make_reference_candidate(
    key="python-style.md",
    content="# Python style\n\nFollow Ruff formatting and 100-character line limits.\n",
    provenance=None,
    category="convention",
    rationale="Distills repo linter configuration.",
):
    return {
        "id": f"references/{key}",
        "category": category,
        "kind": "references",
        "key": key,
        "provenance": provenance if provenance is not None else [{"path": "ruff.toml", "key": "lint.select"}],
        "rationale": rationale,
        "content": content,
    }


def make_script_candidate(
    key="run-checks.sh",
    content="#!/usr/bin/env sh\nset -eu\npython3 -m unittest\n",
    provenance=None,
    executable=True,
):
    cand = {
        "id": f"scripts/{key}",
        "category": "knowledge",
        "kind": "scripts",
        "key": key,
        "provenance": provenance or [{"path": "scripts/verify.sh", "command": "python3 -m unittest"}],
        "content": content,
    }
    if executable is not None:
        cand["executable"] = executable
    return cand


def envelope(*candidates):
    return {"schema_version": 1, "candidates": list(candidates)}


class ExtractAssetsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.repo = self.temp / "target with spaces"
        self.run_command(["git", "init", "-q", self.repo], self.temp)
        self.nested = self.repo / "nested" / "sub"
        self.nested.mkdir(parents=True)
        self.local = self.repo / ".byte-stack"

        # Copy both skill directories to an isolated plugin layout.
        self.skills_root = self.temp / "skills"
        self.bmode_dir = self.skills_root / "bmode"
        self.extract_dir = self.skills_root / "extract-assets"
        shutil.copytree(SKILLS / "bmode", self.bmode_dir)
        shutil.copytree(SKILLS / "extract-assets", self.extract_dir)
        self.extract_script = self.extract_dir / "scripts/extract_assets.py"
        self.capture_script = self.bmode_dir / "scripts/capture_playbook.py"
        self.resolver = self.bmode_dir / "scripts/assets.py"

        # Seed a realistic tracked repository (git add only, no commit).
        self.add_tracked_file(
            ".github/workflows/ci.yml",
            "name: CI\non: [push]\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n      - run: pytest -q\n",
        )
        self.add_tracked_file(
            "Makefile",
            ".PHONY: test lint\ntest:\n\tpython3 -m unittest\nlint:\n\truff check .\n",
        )
        self.add_tracked_file(
            "package.json",
            json.dumps({"name": "demo", "scripts": {"build": "tsc --noEmit", "test": "vitest run"}}, indent=2) + "\n",
        )
        self.add_tracked_file(
            "scripts/verify.sh",
            "#!/usr/bin/env sh\n# Verify repository checks\npython3 -m unittest\n",
            executable=True,
        )
        self.add_tracked_file(
            "AGENTS.md",
            "# Agent Rules\n\n- Always run tests before finishing.\n- Never touch main directly.\n- Keep commits small and focused.\n",
        )
        self.add_tracked_file(
            "docs/adr/0001-architecture.md",
            "# ADR 0001: Architecture\n\n## Decision\n\nUse standard library modules.\n",
        )
        self.add_tracked_file(
            "CONTRIBUTING.md",
            "# Contributing\n\n## Pull Requests\n\n```sh\nmake test\n```\n",
        )
        self.add_tracked_file(
            "ruff.toml",
            "line-length = 100\n\n[lint]\nselect = [\"E\", \"F\"]\n",
        )
        self.add_tracked_file(
            ".pre-commit-config.yaml",
            "repos:\n  - repo: https://example.invalid/hooks\n    hooks:\n      - id: trailing-whitespace\n",
        )
        self.add_tracked_file("src/app.py", "def main():\n    return 0\n")

    def run_command(self, args, cwd, code=0, stdin_text=None):
        result = subprocess.run(
            args,
            cwd=cwd,
            input=stdin_text,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, code, result.stderr + result.stdout)
        return result

    def add_tracked_file(self, rel_path, content, executable=False):
        path = self.repo / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        self.run_command(["git", "add", "-f", rel_path], self.repo)
        return path

    def extract(self, *args, cwd=None, code=0, stdin_text=None, script=None):
        return self.run_command(
            [sys.executable, "-I", script or self.extract_script, *args],
            cwd or self.nested,
            code=code,
            stdin_text=stdin_text,
        )

    def assets(self, *args, cwd=None, code=0):
        return self.run_command(
            [sys.executable, "-I", self.resolver, *args],
            cwd or self.nested,
            code=code,
        )

    def capture(self, *args, cwd=None, code=0):
        return self.run_command(
            [sys.executable, "-I", self.capture_script, *args],
            cwd or self.nested,
            code=code,
        )

    def test_inventory_classification_exclusions_and_determinism(self):
        # Add excluded tracked artifacts: vendored, secret, machine-local, symlink, gitlink.
        self.add_tracked_file("node_modules/pkg/Makefile", "all:\n\techo vendor\n")
        self.add_tracked_file("vendor/lib/package.json", '{"name": "v"}\n')
        self.add_tracked_file("dist/package.json", '{"name": "d"}\n')
        self.add_tracked_file(".venv/scripts/tool.sh", "echo venv\n")
        self.add_tracked_file(".env", "API_KEY=ghp_1234567890abcdefghij\n")
        self.add_tracked_file("certs/dev.pem", "-----BEGIN PRIVATE KEY-----\n")
        self.add_tracked_file("certs/dev.key", "secret\n")
        self.add_tracked_file("id_rsa", "secret\n")
        self.add_tracked_file("credentials.json", '{"token": "secret"}\n')
        self.add_tracked_file("settings.local.json", '{"local": true}\n')
        self.add_tracked_file(".DS_Store", "junk\n")

        # Tracked symlink (mode 120000)
        sym = self.repo / "scripts/link.sh"
        sym.symlink_to(self.repo / "scripts/verify.sh")
        self.run_command(["git", "add", "scripts/link.sh"], self.repo)

        # Tracked submodule gitlink (mode 160000)
        self.run_command(
            ["git", "update-index", "--add", "--cacheinfo", "160000," + ("a" * 40) + ",submod"],
            self.repo,
        )

        # Tracked file replaced by a symlink on disk (must never be read)
        tricky = self.add_tracked_file("scripts/tricky.sh", "echo ok\n")
        outside_secret = self.temp / "outside_secret.txt"
        outside_secret.write_text("SHOULD_NOT_BE_READ\n", encoding="utf-8")
        tricky.unlink()
        tricky.symlink_to(outside_secret)

        # File containing sensitive lines (must drop sensitive signals, keep benign)
        self.add_tracked_file(
            "docs/directives/guide.md",
            "# Safe Heading\n\n```sh\necho ghp_1234567890abcdefghij\necho /home/alice/secret\npytest -q\n```\n",
        )

        # Existing repo .byte-stack asset
        (self.local / "references").mkdir(parents=True)
        (self.local / "references/existing.md").write_text("# Existing\n\nLocal note.\n", encoding="utf-8")

        res1 = self.extract("inventory")
        res2 = self.extract("inventory")
        self.assertEqual(res1.stdout, res2.stdout)

        # Repo root string and sensitive values must never appear in inventory output.
        self.assertNotIn(str(self.repo), res1.stdout)
        self.assertNotIn(str(self.repo.resolve()), res1.stdout)
        self.assertNotIn("SHOULD_NOT_BE_READ", res1.stdout)
        self.assertNotIn("ghp_1234567890abcdefghij", res1.stdout)
        self.assertNotIn("/home/alice/", res1.stdout)

        data = json.loads(res1.stdout)
        cats = data["categories"]
        self.assertEqual([f["path"] for f in cats["ci"]], [".github/workflows/ci.yml"])
        self.assertEqual([f["path"] for f in cats["task_runners"]], ["Makefile", "package.json"])
        self.assertEqual([f["path"] for f in cats["scripts"]], ["scripts/verify.sh"])
        self.assertEqual([f["path"] for f in cats["steering"]], ["AGENTS.md"])
        self.assertEqual([f["path"] for f in cats["adrs"]], ["docs/adr/0001-architecture.md"])
        self.assertEqual([f["path"] for f in cats["directives"]], ["CONTRIBUTING.md", "docs/directives/guide.md"])
        self.assertEqual([f["path"] for f in cats["quality"]], ["ruff.toml"])
        self.assertEqual([f["path"] for f in cats["git_hooks"]], [".pre-commit-config.yaml"])

        # Exclusions recorded by reason.
        excl = data["exclusions"]
        self.assertGreaterEqual(excl.get("vendored_or_build", 0), 4)
        self.assertGreaterEqual(excl.get("secret_file", 0), 5)
        self.assertGreaterEqual(excl.get("machine_local", 0), 2)
        self.assertGreaterEqual(excl.get("symlink", 0), 2)
        self.assertEqual(excl.get("submodule"), 1)
        self.assertGreaterEqual(excl.get("sensitive_signals_dropped", 0), 2)

        # byte_stack includes all four kinds with origin.
        bs = data["byte_stack"]
        self.assertEqual(set(bs.keys()), {"playbooks", "workflows", "references", "scripts"})
        self.assertTrue(any(e["key"] == "investigation.md" and e["origin"] == "bundled" for e in bs["playbooks"]))
        self.assertTrue(any(e["key"] == "existing.md" and e["origin"] == "repo" for e in bs["references"]))
        self.assertEqual(data["diagnostics"], [])

    def test_inventory_bounded_reads_and_truncation(self):
        # Test --max-files
        res_files = json.loads(self.extract("inventory", "--max-files", "2").stdout)
        self.assertEqual(res_files["summary"]["files_read"], 2)
        self.assertTrue(res_files["truncated"]["files"])
        self.assertEqual(res_files["limits"]["max_files"], 2)
        self.assertGreater(res_files["exclusions"].get("max_files_limit", 0), 0)

        # Test --max-bytes
        big_md = "\n".join(f"## Heading {i}\n\nParagraph content line {i}." for i in range(1, 60)) + "\n"
        self.add_tracked_file("docs/directives/big.md", big_md)
        res_bytes = json.loads(self.extract("inventory", "--max-bytes", "120").stdout)
        self.assertTrue(res_bytes["truncated"]["bytes"])
        self.assertLessEqual(res_bytes["summary"]["bytes_read"], 120)

        # Test per-file signal cap (30)
        res_sig = json.loads(self.extract("inventory").stdout)
        big_entry = next(f for f in res_sig["categories"]["directives"] if f["path"] == "docs/directives/big.md")
        self.assertEqual(len(big_entry["signals"]), 30)
        self.assertTrue(big_entry["truncated"])
        self.assertTrue(res_sig["truncated"]["signals"])

    def test_inventory_broken_byte_stack_becomes_diagnostic(self):
        outside = self.temp / "outside"
        outside.mkdir()
        self.local.symlink_to(outside, target_is_directory=True)
        res = self.extract("inventory")
        self.assertNotIn(str(self.repo), res.stdout)
        data = json.loads(res.stdout)
        self.assertTrue(data["diagnostics"])
        self.assertTrue(any("symlink" in d["message"] for d in data["diagnostics"]))
        self.assertTrue(any(e["key"] == "investigation.md" and e["origin"] == "bundled" for e in data["byte_stack"]["playbooks"]))
        self.local.unlink()

        # Broken playbook without Use when: trigger becomes a diagnostic, not a crash.
        (self.local / "playbooks").mkdir(parents=True)
        (self.local / "playbooks/broken.md").write_text("# Broken\n\nNo trigger here.\n", encoding="utf-8")
        res2 = self.extract("inventory")
        self.assertNotIn(str(self.repo), res2.stdout)
        data2 = json.loads(res2.stdout)
        self.assertTrue(any(d["kind"] == "playbooks" and "Use when" in d["message"] for d in data2["diagnostics"]))
        self.assertTrue(any(e["key"] == "investigation.md" and e["origin"] == "bundled" for e in data2["byte_stack"]["playbooks"]))

    def test_missing_bmode_exits_2_and_writes_nothing(self):
        solo_dir = self.temp / "solo/extract-assets"
        shutil.copytree(SKILLS / "extract-assets", solo_dir)
        solo_script = solo_dir / "scripts/extract_assets.py"

        inv_res = self.extract("inventory", code=2, script=solo_script)
        self.assertIn("bmode", inv_res.stderr.lower())

        payload = json.dumps(envelope(make_reference_candidate()))
        wr_res = self.extract("write", "--stdin", "--approve", "references/python-style.md", code=2, stdin_text=payload, script=solo_script)
        self.assertIn("bmode", wr_res.stderr.lower())
        self.assertFalse(self.local.exists())

        # Explicit --bmode works both before and after subcommand.
        self.extract("--bmode", str(self.bmode_dir), "inventory", script=solo_script)
        self.extract("inventory", "--bmode", str(self.bmode_dir), script=solo_script)

    def test_schema_and_provenance_validation(self):
        schema = json.loads(self.extract("schema").stdout)
        self.assertEqual(schema["title"], "ByteStackExtractCandidates")
        self.assertEqual(schema["additionalProperties"], False)

        # Whitespace-normalized command + dotted key + valid line passes dry-run.
        good = make_reference_candidate(
            provenance=[
                {"path": "Makefile", "command": "python3   -m   unittest", "line": 3},
                {"path": "ruff.toml", "key": "lint.select", "line": 4},
            ]
        )
        res = json.loads(self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(envelope(good))).stdout)
        self.assertEqual(res["results"][0]["verdict"], "new")

        # Add an excluded secret file to verify provenance rejects excluded files.
        self.add_tracked_file(".env", "FOO=bar\n")

        invalid_cases = [
            ("{not json", "invalid candidates JSON"),
            (json.dumps({"schema_version": 2, "candidates": []}), "schema_version"),
            (json.dumps({"schema_version": 1, "candidates": [], "extra": 1}), "unknown envelope"),
            (json.dumps(envelope({**make_reference_candidate(), "id": "references/other.md"})), "must equal"),
            (json.dumps(envelope(make_reference_candidate(key="Upper.md"))), "kebab-case"),
            (json.dumps(envelope(make_reference_candidate(key="no-ext"))), "kebab-case"),
            (json.dumps(envelope({**make_reference_candidate(), "executable": True})), "only allowed when kind is 'scripts'"),
            (json.dumps(envelope(make_reference_candidate(provenance=[]))), "non-empty array"),
            (json.dumps(envelope(make_reference_candidate(provenance=[{"path": "untracked.txt"}]))), "not a tracked"),
            (json.dumps(envelope(make_reference_candidate(provenance=[{"path": ".env"}]))), "excluded"),
            (json.dumps(envelope(make_reference_candidate(provenance=[{"path": "Makefile", "command": "cargo test"}]))), "command not found"),
            (json.dumps(envelope(make_reference_candidate(provenance=[{"path": "ruff.toml", "key": "lint.nonexistent"}]))), "segment(s) not found"),
            (json.dumps(envelope(make_reference_candidate(provenance=[{"path": "ruff.toml", "line": 999}]))), "exceeds"),
        ]
        for raw, expected in invalid_cases:
            with self.subTest(expected=expected):
                out = self.extract("write", "--stdin", "--dry-run", code=1, stdin_text=raw)
                self.assertIn(expected, out.stderr + out.stdout)

    def test_dedupe_bundled_existing_and_steering(self):
        # 1. Bundled override (overrides-bundled) requires --override-bundled or --force.
        override_cand = make_playbook_candidate(
            key="investigation.md",
            title="Local investigation",
            use_when="Investigate local service behavior using repo scripts.",
        )
        raw_override = json.dumps(envelope(override_cand))
        conflict = self.extract(
            "write", "--stdin", "--approve", "playbooks/investigation.md", "--json", code=3, stdin_text=raw_override
        )
        cdata = json.loads(conflict.stdout)
        self.assertEqual(cdata["results"][0]["verdict"], "overrides-bundled")
        self.assertEqual(cdata["results"][0]["status"], "conflict")
        self.assertFalse((self.local / "playbooks/investigation.md").exists())

        ok = json.loads(
            self.extract(
                "write",
                "--stdin",
                "--approve",
                "playbooks/investigation.md",
                "--override-bundled",
                "playbooks/investigation.md",
                "--json",
                stdin_text=raw_override,
            ).stdout
        )
        self.assertTrue(ok["results"][0]["written"])
        self.assertTrue((self.local / "playbooks/investigation.md").is_file())

        # Same title as bundled playbook (different key) triggers duplicates-catalog.
        dup_cand = make_playbook_candidate(
            key="dup-feature.md",
            title="Feature",
            use_when="Build brand new behavior with local steps.",
        )
        dup_res = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", code=3, stdin_text=json.dumps(envelope(dup_cand))).stdout
        )
        self.assertEqual(dup_res["results"][0]["verdict"], "duplicates-catalog")

        # 2. Existing .byte-stack/ (exists-identical vs exists-differs).
        rerun = json.loads(
            self.extract(
                "write", "--stdin", "--approve", "playbooks/investigation.md", "--json", stdin_text=raw_override
            ).stdout
        )
        self.assertEqual(rerun["results"][0]["verdict"], "exists-identical")
        self.assertEqual(rerun["results"][0]["status"], "unchanged")

        updated_override = make_playbook_candidate(
            key="investigation.md",
            title="Local investigation v2",
            use_when="Investigate local service behavior using repo scripts.",
        )
        diff_conflict = json.loads(
            self.extract(
                "write", "--stdin", "--approve", "playbooks/investigation.md", "--json", code=3, stdin_text=json.dumps(envelope(updated_override))
            ).stdout
        )
        self.assertEqual(diff_conflict["results"][0]["verdict"], "exists-differs")
        self.assertEqual(diff_conflict["results"][0]["status"], "conflict")

        updated_ok = json.loads(
            self.extract(
                "write",
                "--stdin",
                "--approve",
                "playbooks/investigation.md",
                "--update",
                "playbooks/investigation.md",
                "--json",
                stdin_text=json.dumps(envelope(updated_override)),
            ).stdout
        )
        self.assertEqual(updated_ok["results"][0]["status"], "update")
        self.assertTrue(updated_ok["results"][0]["written"])

        # 3. Standing steering files: steering-only provenance AND >=80% verbatim line match.
        steering_prov = make_reference_candidate(
            key="from-agents.md",
            content="# Unique summary\n\nCompletely reworded guidance.\n",
            provenance=[{"path": "AGENTS.md", "line": 1}],
        )
        sp_res = json.loads(
            self.extract(
                "write", "--stdin", "--approve", "references/from-agents.md", "--json", code=3, stdin_text=json.dumps(envelope(steering_prov))
            ).stdout
        )
        self.assertEqual(sp_res["results"][0]["verdict"], "restates-steering")
        self.assertFalse((self.local / "references/from-agents.md").exists())

        verbatim_steering = make_reference_candidate(
            key="verbatim-agents.md",
            content="# Agent Rules\n\n- Always run tests before finishing.\n- Never touch main directly.\n- Keep commits small and focused.\n",
            provenance=[{"path": "Makefile", "line": 1}],
        )
        vs_res = json.loads(
            self.extract(
                "write", "--stdin", "--approve", "references/verbatim-agents.md", "--json", code=3, stdin_text=json.dumps(envelope(verbatim_steering))
            ).stdout
        )
        self.assertEqual(vs_res["results"][0]["verdict"], "restates-steering")
        self.assertFalse((self.local / "references/verbatim-agents.md").exists())

        # --force overrides restates-steering for that ID.
        vs_forced = json.loads(
            self.extract(
                "write",
                "--stdin",
                "--approve",
                "references/verbatim-agents.md",
                "--force",
                "references/verbatim-agents.md",
                "--json",
                stdin_text=json.dumps(envelope(verbatim_steering)),
            ).stdout
        )
        self.assertTrue(vs_forced["results"][0]["written"])

        # Soft similar_to warning without blocking new verdict.
        soft_cand = make_reference_candidate(
            key="commit-guide.md",
            content="# Commit guide\n\nKeep commits small and focused when preparing pull requests for review.\nVerify automated checks pass locally.\n",
            provenance=[{"path": "CONTRIBUTING.md", "line": 1}],
        )
        soft_res = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(envelope(soft_cand))).stdout
        )
        self.assertEqual(soft_res["results"][0]["verdict"], "new")
        self.assertTrue(any(s["source"] == "steering:AGENTS.md" for s in soft_res["results"][0]["similar_to"]))

    def test_symlink_and_outside_git_guards(self):
        outside = self.temp / "outside"
        outside.mkdir()
        raw = json.dumps(envelope(make_reference_candidate()))

        # Outside Git worktree exits 2.
        self.extract("inventory", cwd=outside, code=2)
        self.extract("write", "--stdin", "--dry-run", cwd=outside, code=2, stdin_text=raw)
        self.assertFalse((outside / ".byte-stack").exists())

        # Symlink at .byte-stack exits 2.
        self.local.symlink_to(outside, target_is_directory=True)
        for extra in (["--dry-run"], ["--approve", "references/python-style.md"]):
            res = self.extract("write", "--stdin", *extra, code=2, stdin_text=raw)
            self.assertIn("symlink", res.stderr)
        self.local.unlink()

        # Symlink at kind directory exits 2.
        self.local.mkdir()
        (self.local / "references").symlink_to(outside, target_is_directory=True)
        res = self.extract("write", "--stdin", "--approve", "references/python-style.md", code=2, stdin_text=raw)
        self.assertIn("symlink", res.stderr)
        (self.local / "references").unlink()

        # Symlink at target file exits 2 and leaves outside victim untouched.
        (self.local / "references").mkdir()
        victim = outside / "victim.md"
        victim.write_text("keep safe", encoding="utf-8")
        target = self.local / "references/python-style.md"
        target.symlink_to(victim)
        self.extract(
            "write",
            "--stdin",
            "--approve",
            "references/python-style.md",
            "--force",
            "references/python-style.md",
            code=2,
            stdin_text=raw,
        )
        self.assertEqual(victim.read_text(encoding="utf-8"), "keep safe")
        target.unlink()

        # Directory at target path exits 2.
        target.mkdir()
        res = self.extract("write", "--stdin", "--approve", "references/python-style.md", code=2, stdin_text=raw)
        self.assertIn("regular file", res.stderr)

    def test_secret_and_local_path_guards_all_four_kinds(self):
        cases = [
            ("playbook secret", make_playbook_candidate(steps=["Export ghp_1234567890abcdefghij before push"]), "secret"),
            ("playbook local", make_playbook_candidate(steps=["Run /home/alice/bin/release.sh"]), "machine-local"),
            ("workflow secret", make_workflow_candidate(steps=["Use sk-1234567890abcdefghij in CI"]), "secret"),
            ("workflow local", make_workflow_candidate(steps=["Read /Users/alice/config.yml"]), "machine-local"),
            ("reference secret", make_reference_candidate(content="# Notes\n\nKey: AKIAIOSFODNN7EXAMPLE\n"), "secret"),
            ("reference local", make_reference_candidate(content="# Notes\n\nPath: C:\\Users\\alice\\repo\n"), "machine-local"),
            ("script secret", make_script_candidate(content="#!/bin/sh\necho '-----BEGIN PRIVATE KEY-----'\n"), "secret"),
            ("script local", make_script_candidate(content="#!/bin/sh\ncd /home/alice/project\n"), "machine-local"),
            ("rationale secret", make_reference_candidate(rationale="Uses ghp_1234567890abcdefghij token"), "secret"),
            ("rationale local", make_reference_candidate(rationale="Copied from /Users/alice/notes"), "machine-local"),
        ]
        for label, cand, expected in cases:
            with self.subTest(label=label):
                out = self.extract("write", "--stdin", "--dry-run", code=1, stdin_text=json.dumps(envelope(cand)))
                self.assertIn(expected, out.stderr + out.stdout)
        self.assertFalse(self.local.exists())

    def test_dry_run_approval_batch_idempotency_and_manual_edit_protection(self):
        pb = make_playbook_candidate()
        wf = make_workflow_candidate()
        ref = make_reference_candidate()
        scr = make_script_candidate()
        all_raw = json.dumps(envelope(pb, wf, ref, scr))

        # --dry-run creates nothing on disk.
        dry = json.loads(self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=all_raw).stdout)
        self.assertEqual(dry["status"], "ok")
        self.assertEqual(len(dry["results"]), 4)
        self.assertFalse(self.local.exists())

        # Non-dry-run without --approve exits 1 and creates nothing.
        no_app = self.extract("write", "--stdin", code=1, stdin_text=all_raw)
        self.assertIn("--approve", no_app.stderr)
        self.assertFalse(self.local.exists())

        # Batch preflight: one invalid candidate aborts the whole batch (writes nothing).
        bad_batch = json.dumps(envelope(ref, make_script_candidate(content="export K=ghp_1234567890abcdefghij\n")))
        self.extract(
            "write",
            "--stdin",
            "--approve",
            "references/python-style.md",
            "--approve",
            "scripts/run-checks.sh",
            code=1,
            stdin_text=bad_batch,
        )
        self.assertFalse(self.local.exists())

        # Write all four approved IDs via --candidates file.
        cand_file = self.temp / "candidates.json"
        cand_file.write_text(all_raw, encoding="utf-8")
        written = json.loads(
            self.extract(
                "write",
                "--candidates",
                str(cand_file),
                "--approve",
                "playbooks/release-notes.md",
                "--approve",
                "workflows/ci-preflight.md",
                "--approve",
                "references/python-style.md",
                "--approve",
                "scripts/run-checks.sh",
                "--json",
            ).stdout
        )
        self.assertEqual(written["status"], "ok")
        self.assertTrue(all(r["written"] and r["resolved_origin"] == "repo" for r in written["results"]))

        # Verify capture_playbook.py validate and assets.py resolve on every written file.
        pb_path = self.local / "playbooks/release-notes.md"
        wf_path = self.local / "workflows/ci-preflight.md"
        ref_path = self.local / "references/python-style.md"
        scr_path = self.local / "scripts/run-checks.sh"

        self.capture("validate", pb_path)
        self.capture("validate", wf_path)
        self.assertEqual(self.assets("resolve", "playbooks", "release-notes.md").stdout.strip(), f"repo\t{pb_path.resolve()}")
        self.assertEqual(self.assets("resolve", "workflows", "ci-preflight.md").stdout.strip(), f"repo\t{wf_path.resolve()}")
        self.assertEqual(self.assets("resolve", "references", "python-style.md").stdout.strip(), f"repo\t{ref_path.resolve()}")
        self.assertEqual(self.assets("resolve", "scripts", "run-checks.sh").stdout.strip(), f"repo\t{scr_path.resolve()}")

        # Script has executable bit; references/ and scripts/ have exact content (no managed marker/sidecar).
        self.assertTrue(scr_path.stat().st_mode & 0o111)
        self.assertEqual(ref_path.read_text(encoding="utf-8"), ref["content"])
        self.assertEqual(scr_path.read_text(encoding="utf-8"), scr["content"])
        self.assertEqual(sorted(p.name for p in (self.local / "references").iterdir()), ["python-style.md"])
        self.assertEqual(sorted(p.name for p in (self.local / "scripts").iterdir()), ["run-checks.sh"])

        # Idempotent rerun: unchanged, zero diff, mtimes preserved.
        stats_before = {p: (p.stat().st_mode, p.stat().st_mtime_ns, p.read_bytes()) for p in (pb_path, wf_path, ref_path, scr_path)}
        rerun = json.loads(
            self.extract(
                "write",
                "--candidates",
                str(cand_file),
                "--approve",
                "playbooks/release-notes.md",
                "--approve",
                "workflows/ci-preflight.md",
                "--approve",
                "references/python-style.md",
                "--approve",
                "scripts/run-checks.sh",
                "--json",
            ).stdout
        )
        self.assertEqual(rerun["status"], "ok")
        self.assertTrue(all(r["status"] == "unchanged" and r["diff"] == "" and not r["written"] for r in rerun["results"]))
        stats_after = {p: (p.stat().st_mode, p.stat().st_mtime_ns, p.read_bytes()) for p in (pb_path, wf_path, ref_path, scr_path)}
        self.assertEqual(stats_before, stats_after)

        # Manual-edit protection on references/ and scripts/ + batch partial skip on conflict.
        edited_ref = ref_path.read_text(encoding="utf-8") + "\nHuman edit.\n"
        ref_path.write_text(edited_ref, encoding="utf-8")
        new_ref = make_reference_candidate(key="git-rules.md", content="# Git rules\n\nRebase locally.\n")
        mixed_raw = json.dumps(envelope(ref, new_ref))
        mixed = json.loads(
            self.extract(
                "write",
                "--stdin",
                "--approve",
                "references/python-style.md",
                "--approve",
                "references/git-rules.md",
                "--json",
                code=3,
                stdin_text=mixed_raw,
            ).stdout
        )
        by_id = {r["id"]: r for r in mixed["results"]}
        self.assertEqual(by_id["references/python-style.md"]["status"], "conflict")
        self.assertIn("Human edit.", by_id["references/python-style.md"]["diff"])
        self.assertEqual(ref_path.read_text(encoding="utf-8"), edited_ref)
        self.assertTrue(by_id["references/git-rules.md"]["written"])
        self.assertTrue((self.local / "references/git-rules.md").is_file())

        # Overwrite differing reference only with --force ID.
        forced = json.loads(
            self.extract(
                "write",
                "--stdin",
                "--approve",
                "references/python-style.md",
                "--force",
                "references/python-style.md",
                "--json",
                stdin_text=json.dumps(envelope(ref)),
            ).stdout
        )
        self.assertEqual(forced["results"][0]["status"], "force-overwrite")
        self.assertEqual(ref_path.read_text(encoding="utf-8"), ref["content"])

    def test_skill_metadata_progressive_disclosure_and_py39_syntax(self):
        bmode_lines = (SKILLS / "bmode/SKILL.md").read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(bmode_lines), 70)

        skill_md = SKILLS / "extract-assets/SKILL.md"
        self.assertTrue(skill_md.is_file())
        skill_lines = skill_md.read_text(encoding="utf-8").splitlines()
        self.assertIn("name: extract-assets", skill_lines)
        desc = next((line.removeprefix("description:").strip() for line in skill_lines if line.startswith("description:")), "")
        self.assertTrue(desc)
        self.assertLessEqual(len(desc), 140)
        self.assertIn("disable-model-invocation: true", skill_lines)

        openai_yaml = SKILLS / "extract-assets/agents/openai.yaml"
        self.assertTrue(openai_yaml.is_file())
        self.assertIn("allow_implicit_invocation: false", openai_yaml.read_text(encoding="utf-8"))

        # References resolve through assets.py --owner "<extract-assets dir>".
        for ref_key in ("extract-assets.md", "extract-candidates.schema.json"):
            resolved = self.assets("--owner", self.extract_dir, "resolve", "references", ref_key).stdout
            self.assertIn("bundled\t", resolved)

        self.assertTrue((ROOT / "docs/adr/byte-stack-extract.md").is_file())

        # Python 3.9 syntax check via ast.parse(..., feature_version=(3, 9)).
        for py_file in (SKILLS / "extract-assets/scripts/extract_assets.py", Path(__file__).resolve()):
            ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file), feature_version=(3, 9))


if __name__ == "__main__":
    unittest.main()
