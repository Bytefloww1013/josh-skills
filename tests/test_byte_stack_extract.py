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
        "provenance": provenance or [{"path": "Makefile", "command": "python3 -m unittest", "line": 3}],
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
            (json.dumps(envelope(make_reference_candidate(provenance=[{"path": "ruff.toml", "key": "lint.nonexistent"}]))), "key not found"),
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

        # --allow-duplicate overrides restates-steering for that ID (while --force alone does not).
        self.extract(
            "write", "--stdin", "--approve", "references/verbatim-agents.md",
            "--force", "references/verbatim-agents.md", "--json", code=3,
            stdin_text=json.dumps(envelope(verbatim_steering)),
        )
        self.assertFalse((self.local / "references/verbatim-agents.md").exists())
        vs_forced = json.loads(
            self.extract(
                "write",
                "--stdin",
                "--approve",
                "references/verbatim-agents.md",
                "--allow-duplicate",
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

        # A8: if SKILL.md advertises argument-hint, its body defines both arguments.
        skill_text = skill_md.read_text(encoding="utf-8")
        if any(line.startswith("argument-hint:") for line in skill_lines):
            self.assertIn("category", skill_text.lower())
            self.assertIn("--dry-run", skill_text)
            self.assertRegex(skill_text, r"(?i)restrict|filter|only that category|stop after")

        # A9, A3, A5, R2: ADR, guide, and README reflect local-only checks, no-op identical flag, mid-run I/O note, and rename window.
        adr_text = (ROOT / "docs/adr/byte-stack-extract.md").read_text(encoding="utf-8")
        guide_text = (SKILLS / "extract-assets/references/extract-assets.md").read_text(encoding="utf-8")
        readme_text = (ROOT / "plugins/byte-stack/README.md").read_text(encoding="utf-8")
        self.assertNotIn("Local + CI", adr_text)
        self.assertIn("exists-identical", adr_text)
        self.assertIn("exists-identical", readme_text)
        self.assertRegex(adr_text, r"(?i)unexpected i/o|mid-run")
        for doc in (adr_text, guide_text):
            self.assertRegex(doc, r"(?i)no-clobber")
            self.assertRegex(doc, r"(?i)can be lost")
            self.assertNotIn("turning post-preflight changes into", doc)
            self.assertNotIn("so post-preflight changes become", doc)

    def test_inventory_redaction_budgets_exclusions_and_lean_output(self):
        # B1: compact JSON by default; --pretty produces indented JSON.
        compact = self.extract("inventory")
        self.assertEqual(len(compact.stdout.strip().splitlines()), 1)
        pretty = self.extract("inventory", "--pretty")
        self.assertGreater(len(pretty.stdout.strip().splitlines()), 10)
        self.assertEqual(json.loads(compact.stdout), json.loads(pretty.stdout))

        # B1: scripts emit at most one summary signal (first comment/docstring line) and do not trip truncated.signals.
        self.add_tracked_file(
            "scripts/multi.py",
            "#!/usr/bin/env python3\n"
            '"""Build release bundle."""\n'
            "# Second comment ignored\n"
            "def alpha():\n    pass\n"
            "def beta():\n    pass\n"
            "def gamma():\n    pass\n",
            executable=True,
        )
        # B3: .claude/settings.json is hooks config, not steering.
        self.add_tracked_file(
            ".claude/settings.json",
            '{"hooks": {"PreToolUse": [{"command": "node scripts/hook.js"}]}}\n',
        )
        # A2: directory-segment exclusions (.local) and non-home absolute paths (C2) stay visible.
        self.add_tracked_file("scripts/.local/verify.sh", "#!/bin/sh\necho local\n", executable=True)
        self.add_tracked_file("docs/directives/paths.md", "# Logs /var/lib/fixture/results\n\nSafe body.\n")

        inv = json.loads(self.extract("inventory").stdout)
        script_paths = [f["path"] for f in inv["categories"]["scripts"]]
        self.assertNotIn("scripts/.local/verify.sh", script_paths)
        self.assertIn(".claude/settings.json", [f["path"] for f in inv["categories"]["git_hooks"]])
        self.assertNotIn(".claude/settings.json", [f["path"] for f in inv["categories"]["steering"]])
        multi = next(f for f in inv["categories"]["scripts"] if f["path"] == "scripts/multi.py")
        self.assertEqual(len(multi["signals"]), 1)
        self.assertEqual(multi["signals"][0]["line"], 2)
        self.assertIn("Build release bundle.", multi["signals"][0]["text"])
        self.assertFalse(multi["truncated"])
        self.assertFalse(inv["truncated"]["signals"])
        self.assertIn("/var/lib/fixture/results", json.dumps(inv))

        # B3: citing .claude/settings.json alone must not trigger restates-steering.
        hook_ref = make_reference_candidate(
            key="hook-policy.md",
            content="# Hook policy\n\nUse PreToolUse hooks defined in settings.\n",
            provenance=[{"path": ".claude/settings.json", "key": "hooks.PreToolUse"}],
        )
        hook_res = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(envelope(hook_ref))).stdout
        )
        self.assertEqual(hook_res["results"][0]["verdict"], "new")

        # A1, A2, C2, C4: catalog redaction, catalog exclusions, and bounded 4 KiB head + shared budget.
        fake_token = "sk-" + ("m" * 21)
        (self.local / "playbooks").mkdir(parents=True, exist_ok=True)
        (self.local / "references/vendor").mkdir(parents=True, exist_ok=True)
        (self.local / "scripts").mkdir(parents=True, exist_ok=True)
        (self.local / "playbooks/sensitive.md").write_text(
            f"# Sensitive\n\nUse when: Inspect {fake_token} /home/fixture/file {self.repo}\n",
            encoding="utf-8",
        )
        tail_marker = "catalog-tail-marker"
        (self.local / "playbooks/large.md").write_text(
            "# Large\n" + ("x" * 1024 + "\n") * 8 + f"Use when: {tail_marker}\n",
            encoding="utf-8",
        )
        (self.local / "references/vendor/readme.md").write_text("# Vendored\n", encoding="utf-8")
        (self.local / "references/readme.local.md").write_text("# Local\n", encoding="utf-8")
        (self.local / "references/secret.key").write_text("SECRET_KEY_BODY\n", encoding="utf-8")
        (self.local / "scripts/credentials.json").write_text('{"token": "abc"}\n', encoding="utf-8")

        inv_full = self.extract("inventory")
        self.assertNotIn(fake_token, inv_full.stdout)
        self.assertNotIn("/home/fixture/file", inv_full.stdout)
        self.assertNotIn(str(self.repo), inv_full.stdout)
        self.assertNotIn(str(self.repo.resolve()), inv_full.stdout)
        self.assertNotIn(tail_marker, inv_full.stdout)
        full_data = json.loads(inv_full.stdout)
        repo_keys = [
            (k, e["key"]) for k, entries in full_data["byte_stack"].items() for e in entries if e["origin"] == "repo"
        ]
        self.assertNotIn(("references", "vendor/readme.md"), repo_keys)
        self.assertNotIn(("references", "readme.local.md"), repo_keys)
        self.assertNotIn(("references", "secret.key"), repo_keys)
        self.assertNotIn(("scripts", "credentials.json"), repo_keys)
        self.assertTrue(any("large.md" in d["message"] for d in full_data["diagnostics"]))

        # Shared budget with --max-files 1 --max-bytes 1 must not read catalog files or leak root.
        inv_tiny = self.extract("inventory", "--max-files", "1", "--max-bytes", "1")
        tiny_data = json.loads(inv_tiny.stdout)
        self.assertEqual(tiny_data["summary"]["files_read"], 1)
        self.assertEqual(tiny_data["summary"]["bytes_read"], 1)
        self.assertNotIn(str(self.repo), inv_tiny.stdout)
        self.assertEqual(
            [e["key"] for entries in tiny_data["byte_stack"].values() for e in entries if e["origin"] == "repo"],
            [],
        )

        # A2: binary files are charged to --max-files / --max-bytes before discarding.
        bin_repo = self.temp / "bin-repo"
        self.run_command(["git", "init", "-q", bin_repo], self.temp)
        for i in range(4):
            p = bin_repo / f"scripts/{i}.sh"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"\x00" + b"x" * 200)
            self.run_command(["git", "add", "-f", f"scripts/{i}.sh"], bin_repo)
        bin_inv = json.loads(self.extract("inventory", "--cwd", str(bin_repo), "--max-files", "2", "--max-bytes", "100").stdout)
        self.assertLessEqual(bin_inv["summary"]["files_read"], 2)
        self.assertLessEqual(bin_inv["summary"]["bytes_read"], 100)
        self.assertEqual(bin_inv["exclusions"].get("binary"), 1)
        self.assertEqual(bin_inv["exclusions"].get("max_bytes_limit", 0) + bin_inv["exclusions"].get("max_files_limit", 0), 3)

    def test_provenance_boundaries_line_scoping_and_package_signals(self):
        # A4: package.json inventory emits citable command & key separately.
        inv = json.loads(self.extract("inventory").stdout)
        pkg = next(f for f in inv["categories"]["task_runners"] if f["path"] == "package.json")
        test_sig = next(s for s in pkg["signals"] if s["kind"] == "command" and "vitest run" in s["text"])
        self.assertEqual(test_sig["text"], "vitest run")
        self.assertEqual(test_sig.get("key"), "scripts.test")

        pkg_cand = make_reference_candidate(
            key="pkg-test.md",
            content="# Package test\n\nRun vitest for JS packages.\n",
            provenance=[{"path": "package.json", "command": test_sig["text"], "key": test_sig["key"], "line": test_sig["line"]}],
        )
        ok = json.loads(self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(envelope(pkg_cand))).stdout)
        self.assertEqual(ok["results"][0]["verdict"], "new")

        # A4: token boundaries and line scoping reject loose substring/wrong-line provenance.
        self.add_tracked_file(
            "scripts/multi-cmd.mk",
            "check:\n\tdev-guardtest suite\n\tpython3 -m \\\n\t  unittest\n",
        )
        bad_sub = make_reference_candidate(
            provenance=[{"path": "scripts/multi-cmd.mk", "command": "guardtest suite", "line": 1}],
        )
        self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=json.dumps(envelope(bad_sub)))

        bad_sub_right_line = make_reference_candidate(
            provenance=[{"path": "scripts/multi-cmd.mk", "command": "guardtest suite", "line": 2}],
        )
        self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=json.dumps(envelope(bad_sub_right_line)))

        bad_wrong_line = make_reference_candidate(
            provenance=[{"path": "scripts/multi-cmd.mk", "command": "dev-guardtest suite", "line": 1}],
        )
        self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=json.dumps(envelope(bad_wrong_line)))

        bad_key_sub = make_reference_candidate(
            provenance=[{"path": "ruff.toml", "key": "length"}],
        )
        self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=json.dumps(envelope(bad_key_sub)))

        bad_key_line = make_reference_candidate(
            provenance=[{"path": "ruff.toml", "key": "lint.select", "line": 1}],
        )
        self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=json.dumps(envelope(bad_key_line)))

        # Multi-line backslash-continued command passes at its starting line.
        good_multiline = make_reference_candidate(
            provenance=[{"path": "scripts/multi-cmd.mk", "command": "python3 -m unittest", "line": 3}],
        )
        good_res = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(envelope(good_multiline))).stdout
        )
        self.assertEqual(good_res["results"][0]["verdict"], "new")

    def test_dedupe_bytes_crlf_same_content_steering_batch_and_similar_to(self):
        # A5: byte-identical script under a different key is duplicates-catalog (conflict).
        (self.local / "scripts").mkdir(parents=True, exist_ok=True)
        (self.local / "scripts/old.sh").write_bytes(b"printf 'hello\\n'\n")
        dup_scr = make_script_candidate(key="new.sh", content="printf 'hello\\n'\n")
        dup_res = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", code=3, stdin_text=json.dumps(envelope(dup_scr))).stdout
        )
        self.assertEqual(dup_res["results"][0]["verdict"], "duplicates-catalog")
        self.assertEqual(dup_res["results"][0]["status"], "conflict")

        # A5: unbulleted lines matching bulleted steering + fresh line is NOT hard restates-steering, only soft similar_to.
        self.add_tracked_file(
            "AGENTS.md",
            "# House rules\n\n- Rule Alpha\n- Rule Beta\n- Rule Gamma\n- Rule Delta\n",
        )
        unbulleted = make_reference_candidate(
            key="unbulleted.md",
            content="Rule Alpha\nRule Beta\nRule Gamma\nRule Delta\nA fresh rule\n",
            provenance=[{"path": "Makefile"}],
        )
        ub_res = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(envelope(unbulleted))).stdout
        )
        self.assertEqual(ub_res["results"][0]["verdict"], "new")
        self.assertEqual(ub_res["results"][0]["status"], "create")
        self.assertTrue(any(s["source"] == "steering:AGENTS.md" for s in ub_res["results"][0]["similar_to"]))

        # A5, C10: CRLF on disk vs LF candidate reports exists-differs / conflict and mentions line endings.
        (self.local / "references").mkdir(parents=True, exist_ok=True)
        crlf_path = self.local / "references/python-style.md"
        ref = make_reference_candidate()
        crlf_bytes = ref["content"].replace("\n", "\r\n").encode("utf-8")
        crlf_path.write_bytes(crlf_bytes)
        crlf_res = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", code=3, stdin_text=json.dumps(envelope(ref))).stdout
        )
        self.assertEqual(crlf_res["results"][0]["verdict"], "exists-differs")
        self.assertEqual(crlf_res["results"][0]["status"], "conflict")
        self.assertIn("line ending", (crlf_res["results"][0]["reason"] + crlf_res["results"][0]["diff"]).lower())
        self.assertEqual(crlf_path.read_bytes(), crlf_bytes)
        crlf_path.unlink()

        # C9: two playbooks in one batch with same title & trigger -> second is duplicates-catalog in preview and write.
        pb1 = make_playbook_candidate(key="unique-one.md", title="Unique flow", use_when="Run unique flow across packages.")
        pb2 = make_playbook_candidate(key="unique-two.md", title="Unique flow", use_when="Run unique flow across packages.")
        batch_raw = json.dumps(envelope(pb1, pb2))
        dry_batch = json.loads(self.extract("write", "--stdin", "--dry-run", "--json", code=3, stdin_text=batch_raw).stdout)
        self.assertEqual([r["status"] for r in dry_batch["results"]], ["create", "conflict"])
        self.assertEqual([r["verdict"] for r in dry_batch["results"]], ["new", "duplicates-catalog"])
        wr_batch = json.loads(
            self.extract(
                "write", "--stdin", "--approve", pb1["id"], "--approve", pb2["id"], "--json", code=3, stdin_text=batch_raw
            ).stdout
        )
        self.assertEqual([r["status"] for r in wr_batch["results"]], ["create", "conflict"])
        self.assertTrue((self.local / "playbooks/unique-one.md").is_file())
        self.assertFalse((self.local / "playbooks/unique-two.md").exists())

        # B2: scoped similar_to (branch-naming ref silent against opening-a-pr playbook; script silent against references; cap at 3).
        branch_ref = make_reference_candidate(
            key="branch-naming.md",
            content="# Branch naming\n\nUse Conventional Commit type to match the pull request branch descriptor.\n",
            provenance=[{"path": "CONTRIBUTING.md"}],
        )
        br_res = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(envelope(branch_ref))).stdout
        )
        self.assertFalse(any("opening-a-pr.md" in s["source"] for s in br_res["results"][0]["similar_to"]))

        short_scr = make_script_candidate(
            key="check-brief.sh",
            content="#!/bin/sh\n# implementor brief report status checks\necho done\n",
        )
        scr_res = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(envelope(short_scr))).stdout
        )
        self.assertEqual(scr_res["results"][0]["similar_to"], [])

        # Cap similar_to at 3 even when >3 references share title tokens.
        for i in range(5):
            (self.local / f"references/style-{i}.md").write_text(f"# Python formatting style guide {i}\n\nNotes.\n", encoding="utf-8")
        style_cand = make_reference_candidate(
            key="style-new.md",
            content="# Python formatting style guide\n\nDetails.\n",
        )
        st_res = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(envelope(style_cand))).stdout
        )
        self.assertLessEqual(len(st_res["results"][0]["similar_to"]), 3)

    def test_write_safety_redacted_diffs_bare_home_and_malformed_types(self):
        # A1: existing sensitive file diff is visibly redacted for both references and playbooks.
        marker = "ghp_" + ("A" * 20)
        (self.local / "references").mkdir(parents=True, exist_ok=True)
        (self.local / "references/python-style.md").write_text(
            f"# Python style\n\nSafe context line.\n{marker}\n", encoding="utf-8"
        )
        ref = make_reference_candidate()
        ref_dry = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", code=3, stdin_text=json.dumps(envelope(ref))).stdout
        )
        self.assertNotIn(marker, ref_dry["results"][0]["diff"])
        self.assertIn("REDACTED", ref_dry["results"][0]["diff"])
        self.assertIn("Safe context line.", ref_dry["results"][0]["diff"])

        (self.local / "playbooks").mkdir(parents=True, exist_ok=True)
        (self.local / "playbooks/release-notes.md").write_text(
            f"# Release notes\n\nUse when: Prepare release notes.\n\nToken: {marker}\n", encoding="utf-8"
        )
        pb = make_playbook_candidate()
        pb_dry = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", code=3, stdin_text=json.dumps(envelope(pb))).stdout
        )
        self.assertNotIn(marker, pb_dry["results"][0]["diff"])
        self.assertIn("REDACTED", pb_dry["results"][0]["diff"])

        # C7: bare /home/<user>, /Users/<user>, and C:\Users\<user> without trailing slash rejected across all 4 kinds and inventory.
        bare_cases = [
            ("pb-home", make_playbook_candidate(steps=["Use /home/fixture for state"])),
            ("wf-users", make_workflow_candidate(steps=["Inspect /Users/fixture before release"])),
            ("ref-home", make_reference_candidate(content="# Notes\n\nDir is /home/fixture.\n")),
            ("scr-win", make_script_candidate(content="#!/bin/sh\necho 'C:\\Users\\fixture'\n")),
        ]
        for label, cand in bare_cases:
            with self.subTest(label=label):
                out = self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=json.dumps(envelope(cand)))
                data = json.loads(out.stdout)
                self.assertTrue(any("machine-local" in e for e in data["errors"]), data)
        self.add_tracked_file("docs/directives/bare-home.md", "# Guide /home/fixture\n\n# Safe title\n")
        inv_bare = self.extract("inventory")
        self.assertNotIn("/home/fixture", inv_bare.stdout)
        self.assertIn("Safe title", inv_bare.stdout)

        # A6, C8: malformed key types and lone surrogates return structured JSON errors (exit 1), no traceback.
        for label, bad_cand in (
            ("list-key", {**make_reference_candidate(), "key": ["x"], "category": "bogus"}),
            ("int-key", {**make_reference_candidate(), "key": 1}),
            ("surrogate-content", make_reference_candidate(content="# Sample\ud800\n")),
        ):
            with self.subTest(label=label):
                out = self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=json.dumps(envelope(bad_cand)))
                self.assertNotIn("Traceback", out.stderr)
                parsed = json.loads(out.stdout)
                self.assertEqual(parsed["status"], "invalid")
                self.assertTrue(parsed["errors"])
                if label == "list-key":
                    self.assertGreaterEqual(len(parsed["errors"]), 2)

    def test_preflight_validation_collisions_toctou_and_capture_handoff(self):
        # A3, C1: invalid reference (conflicting triggers) rejected at preflight without touching existing file.
        (self.local / "references").mkdir(parents=True, exist_ok=True)
        existing = self.local / "references/trigger.md"
        existing.write_text("# Hand-authored\n\nKeep me.\n", encoding="utf-8")
        bad_ref = make_reference_candidate(
            key="trigger.md",
            content="---\nuse-when: Alpha\n---\n# Reference\n\nUse when: Beta\n",
        )
        raw_bad = json.dumps(envelope(bad_ref))
        dry = self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=raw_bad)
        self.assertIn("trigger", dry.stdout.lower())
        self.extract(
            "write", "--stdin", "--approve", bad_ref["id"], "--force", bad_ref["id"], "--json", code=1, stdin_text=raw_bad
        )
        self.assertEqual(existing.read_text(encoding="utf-8"), "# Hand-authored\n\nKeep me.\n")
        existing.unlink()

        # A3, C5: ancestor/descendant target collision rejected at preflight in preview and write.
        c_parent = make_script_candidate(key="bundle", content="#!/bin/sh\necho bundle\n")
        c_child = make_script_candidate(key="bundle/check.sh", content="#!/bin/sh\necho child\n")
        col_raw = json.dumps(envelope(c_parent, c_child))
        col_dry = self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=col_raw)
        self.assertIn("collision", col_dry.stdout.lower())
        self.extract(
            "write", "--stdin", "--approve", c_parent["id"], "--approve", c_child["id"], "--json", code=1, stdin_text=col_raw
        )
        self.assertFalse((self.local / "scripts/bundle").exists())

        # C6: repo whose own path contains .byte-stack/playbooks validates capture writes cleanly.
        nested_repo = self.temp / ".byte-stack/playbooks/nested-repo"
        nested_repo.mkdir(parents=True)
        self.run_command(["git", "init", "-q", nested_repo], self.temp)
        mk = nested_repo / "Makefile"
        mk.write_text("test:\n\tpython3 -m unittest\n", encoding="utf-8")
        self.run_command(["git", "add", "Makefile"], nested_repo)
        pb_nested = make_playbook_candidate(provenance=[{"path": "Makefile", "command": "python3 -m unittest", "line": 2}])
        nested_out = json.loads(
            self.extract(
                "write", "--stdin", "--cwd", str(nested_repo), "--approve", pb_nested["id"], "--json",
                stdin_text=json.dumps(envelope(pb_nested)),
            ).stdout
        )
        self.assertTrue(nested_out["results"][0]["written"])
        self.assertTrue(nested_out["results"][0]["validated"])

        # C3 & C6: TOCTOU race on create, force-overwrite, and late conflict on capture write return per-ID conflict (exit 3).
        race_helper = (
            "import json, runpy, sys\n"
            "from pathlib import Path\n"
            "from unittest.mock import patch\n"
            "cli, repo, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]\n"
            "m = runpy.run_path(str(cli))\n"
            "g = m['cmd_write'].__globals__\n"
            "if mode == 'ref-create':\n"
            "    real = g['_plan_candidate']\n"
            "    def hook(*a, **kw):\n"
            "        res = real(*a, **kw)\n"
            "        t = repo / '.byte-stack/references/race.md'\n"
            "        t.parent.mkdir(parents=True, exist_ok=True)\n"
            "        t.write_text('Human notes\\n', encoding='utf-8')\n"
            "        return res\n"
            "    with patch.dict(g, {'_plan_candidate': hook}):\n"
            "        args = m['build_parser']().parse_args(sys.argv[4:])\n"
            "        sys.exit(m['cmd_write'](args))\n"
            "elif mode == 'ref-force':\n"
            "    real = g['_plan_candidate']\n"
            "    def hook(*a, **kw):\n"
            "        res = real(*a, **kw)\n"
            "        t = repo / '.byte-stack/references/race-force.md'\n"
            "        t.write_text('# Concurrent human edit\\n', encoding='utf-8')\n"
            "        return res\n"
            "    with patch.dict(g, {'_plan_candidate': hook}):\n"
            "        args = m['build_parser']().parse_args(sys.argv[4:])\n"
            "        sys.exit(m['cmd_write'](args))\n"
            "else:\n"
            "    real = g['_run_capture_subprocess']\n"
            "    def hook(exe, cargs, stdin_text=None):\n"
            "        if cargs[0] == 'write' and '--dry-run' not in cargs:\n"
            "            t = repo / '.byte-stack/workflows/race-wf.md'\n"
            "            t.parent.mkdir(parents=True, exist_ok=True)\n"
            "            t.write_text('# Human workflow\\n', encoding='utf-8')\n"
            "        return real(exe, cargs, stdin_text=stdin_text)\n"
            "    with patch.dict(g, {'_run_capture_subprocess': hook}):\n"
            "        args = m['build_parser']().parse_args(sys.argv[4:])\n"
            "        sys.exit(m['cmd_write'](args))\n"
        )
        race_ref = make_reference_candidate(key="race.md")
        r1 = self.run_command(
            [
                sys.executable, "-I", "-c", race_helper, str(self.extract_script), str(self.repo), "ref-create",
                "write", "--stdin", "--json", "--cwd", str(self.repo), "--approve", race_ref["id"],
            ],
            self.nested,
            code=3,
            stdin_text=json.dumps(envelope(race_ref)),
        )
        r1_data = json.loads(r1.stdout)
        self.assertEqual(r1_data["results"][0]["status"], "conflict")
        self.assertEqual((self.local / "references/race.md").read_text(encoding="utf-8"), "Human notes\n")

        force_target = self.local / "references/race-force.md"
        force_target.write_text("# Reviewed old notes\n", encoding="utf-8")
        race_force = make_reference_candidate(key="race-force.md")
        r1b = self.run_command(
            [
                sys.executable, "-I", "-c", race_helper, str(self.extract_script), str(self.repo), "ref-force",
                "write", "--stdin", "--json", "--cwd", str(self.repo),
                "--approve", race_force["id"], "--force", race_force["id"],
            ],
            self.nested,
            code=3,
            stdin_text=json.dumps(envelope(race_force)),
        )
        r1b_data = json.loads(r1b.stdout)
        self.assertEqual(r1b_data["results"][0]["status"], "conflict")
        self.assertEqual(force_target.read_text(encoding="utf-8"), "# Concurrent human edit\n")

        race_wf = make_workflow_candidate(key="race-wf.md")
        unrelated_ref = make_reference_candidate(key="unrelated-after-race.md", content="# Unrelated\n\nStill written.\n")
        r2 = self.run_command(
            [
                sys.executable, "-I", "-c", race_helper, str(self.extract_script), str(self.repo), "cap-late",
                "write", "--stdin", "--json", "--cwd", str(self.repo),
                "--approve", race_wf["id"], "--approve", unrelated_ref["id"],
            ],
            self.nested,
            code=3,
            stdin_text=json.dumps(envelope(race_wf, unrelated_ref)),
        )
        r2_data = json.loads(r2.stdout)
        by_id = {r["id"]: r for r in r2_data["results"]}
        self.assertEqual(by_id[race_wf["id"]]["status"], "conflict")
        self.assertFalse(by_id[race_wf["id"]]["written"])
        self.assertEqual(by_id[unrelated_ref["id"]]["status"], "create")
        self.assertTrue(by_id[unrelated_ref["id"]]["written"])
        self.assertTrue((self.local / "references/unrelated-after-race.md").is_file())

    def test_r1_output_boundary_non_ascii_home_partial_line_and_root_prefix(self):
        token = "ghp_" + ("A" * 20)
        home = "/home/sample-user"

        # Secret marker in tracked paths is excluded from inventory, not emitted redacted.
        self.add_tracked_file(f"scripts/{token}.sh", "#!/bin/sh\n# Harmless summary\n", executable=True)
        self.add_tracked_file(f"docs/directives/{token}.md", "# Shared package conventions\n")

        # Whole-path-prefix repo root matching: docs/<root without leading slash>/Makefile stays intact,
        # while a real repo-root path inside a trigger is redacted to <repo>.
        root_no_slash = str(self.repo.resolve()).lstrip("/")
        root_named_mk = f"docs/{root_no_slash}/Makefile"
        self.add_tracked_file(root_named_mk, "check:\n\tpython3 -m unittest\n")
        (self.local / "playbooks").mkdir(parents=True, exist_ok=True)
        (self.local / "playbooks/root-trig.md").write_text(
            f"# Root trigger\n\nUse when: Inspect {self.repo} {home} {token}\n", encoding="utf-8"
        )

        inv_res = self.extract("inventory")
        self.assertNotIn(token, inv_res.stdout)
        self.assertNotIn(home, inv_res.stdout)
        inv_without_fixture_path = inv_res.stdout.replace(root_named_mk, "")
        self.assertNotIn(str(self.repo), inv_without_fixture_path)
        self.assertNotIn(str(self.repo.resolve()), inv_without_fixture_path)
        inv = json.loads(inv_res.stdout)
        trig = next(e["trigger"] for e in inv["byte_stack"]["playbooks"] if e["key"] == "root-trig.md")
        self.assertEqual(trig, "Inspect <repo> <local-path> <redacted-secret>")
        all_paths = [f["path"] for files in inv["categories"].values() for f in files]
        self.assertNotIn(f"scripts/{token}.sh", all_paths)
        self.assertNotIn(f"docs/directives/{token}.md", all_paths)
        self.assertFalse(any("<redacted-secret>" in p for p in all_paths))
        self.assertIn(root_named_mk, all_paths)

        # Fixture file under docs/<root without leading slash>/Makefile is accepted as provenance.
        root_path_cand = make_reference_candidate(
            key="root-prefix-ok.md",
            content="# Root prefix\n\nProvenance path containing the root segment stays valid.\n",
            provenance=[{"path": root_named_mk, "command": "python3 -m unittest", "line": 2}],
        )
        rp_out = json.loads(
            self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(envelope(root_path_cand))).stdout
        )
        self.assertEqual(rp_out["results"][0]["status"], "create")
        self.assertEqual(rp_out["results"][0]["provenance"][0]["path"], root_named_mk)

        # Secret marker in duplicate filename must not leak in verdict_reason.
        (self.local / "scripts").mkdir(parents=True, exist_ok=True)
        dup_scr = make_script_candidate(key="dup-check.sh")
        (self.local / f"scripts/{token}.sh").write_text(dup_scr["content"], encoding="utf-8")
        dup_out = self.extract("write", "--stdin", "--dry-run", "--json", code=3, stdin_text=json.dumps(envelope(dup_scr)))
        self.assertNotIn(token, dup_out.stdout + dup_out.stderr)
        dup_data = json.loads(dup_out.stdout)
        self.assertEqual(dup_data["results"][0]["verdict"], "duplicates-catalog")
        self.assertNotIn(token, dup_data["results"][0]["verdict_reason"])

        # Secret marker and home path echoed in unknown-field validation errors are redacted in JSON and stderr.
        bad_field_cand = make_reference_candidate()
        bad_field_cand[f"unused-{token}{home}"] = True
        for extra in (["--dry-run", "--json"], ["--dry-run"]):
            err_res = self.extract("write", "--stdin", *extra, code=1, stdin_text=json.dumps(envelope(bad_field_cand)))
            self.assertNotIn(token, err_res.stdout + err_res.stderr)
            self.assertNotIn(home, err_res.stdout + err_res.stderr)

        # Repo root inside an accepted provenance command must not leak in preview JSON or text output.
        # Use a /tmp-rooted repo when available so the checkout path itself is not under /home/.
        tmp_base = Path("/tmp") if Path("/tmp").is_dir() else self.temp
        with tempfile.TemporaryDirectory(dir=tmp_base) as root_dir:
            root_repo = Path(root_dir) / "repo-root-prov"
            root_repo.mkdir()
            self.run_command(["git", "init", "-q", root_repo], root_repo)
            (root_repo / "Makefile").write_text(f"check:\n\tgit -C {root_repo} status\n", encoding="utf-8")
            self.run_command(["git", "add", "Makefile"], root_repo)
            root_prov_cand = make_script_candidate(
                key="root-prov.sh",
                provenance=[{"path": "Makefile", "line": 2, "command": f"git -C {root_repo} status"}],
            )
            for extra in (["--dry-run", "--json"], ["--dry-run"]):
                res_rp = self.extract("write", "--stdin", "--cwd", str(root_repo), *extra, stdin_text=json.dumps(envelope(root_prov_cand)))
                self.assertNotIn(str(root_repo), res_rp.stdout + res_rp.stderr)
                self.assertNotIn(str(root_repo.resolve()), res_rp.stdout + res_rp.stderr)

        # Non-ASCII home paths rejected across write and dropped/redacted in inventory.
        for literal in ("/home/équipe", "/Users/josé", "C:\\Users\\équipe"):
            with self.subTest(literal=literal):
                cand = make_reference_candidate(content=f"# Guide\n\nInspect {literal} locally.\n")
                out = self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=json.dumps(envelope(cand)))
                self.assertIn("machine-local", out.stdout)
                self.assertNotIn(literal, out.stdout + out.stderr)

        # Signal cut mid-line by --max-bytes drops the unfinished line and sets truncation flag.
        cut_repo = self.temp / "cut-repo"
        self.run_command(["git", "init", "-q", cut_repo], self.temp)
        (cut_repo / "docs/directives").mkdir(parents=True)
        (cut_repo / "docs/directives/cut.md").write_text(f"# Safe heading {token}\n", encoding="utf-8")
        self.run_command(["git", "add", "docs/directives/cut.md"], cut_repo)
        limit = len("# Safe heading ghp_") + 15
        cut_inv = json.loads(self.extract("inventory", "--cwd", str(cut_repo), "--max-bytes", str(limit)).stdout)
        self.assertTrue(cut_inv["truncated"]["bytes"])
        self.assertEqual(cut_inv["categories"]["directives"][0]["signals"], [])
        self.assertNotIn("ghp_", json.dumps(cut_inv))

        # Long script summary clipped to MAX_SIGNAL_TEXT_LEN sets truncated flags honestly.
        (cut_repo / "scripts").mkdir(parents=True)
        (cut_repo / "scripts/long.sh").write_text("# " + ("x" * 230) + "\n", encoding="utf-8")
        self.run_command(["git", "add", "scripts/long.sh"], cut_repo)
        long_inv = json.loads(self.extract("inventory", "--cwd", str(cut_repo)).stdout)
        long_entry = long_inv["categories"]["scripts"][0]
        self.assertTrue(long_entry["truncated"])
        self.assertTrue(long_inv["truncated"]["signals"])

    def test_r3_unbuffered_byte_budget_and_env_segment_exclusion(self):
        # .env* exclusion applies to every path segment (including .envrc/Makefile).
        self.add_tracked_file(".envrc/Makefile", "all:\n\techo envrc\n")
        self.add_tracked_file("sub/.envrc/tool.sh", "#!/bin/sh\necho envrc\n", executable=True)
        inv = json.loads(self.extract("inventory").stdout)
        all_paths = [f["path"] for files in inv["categories"].values() for f in files]
        self.assertNotIn(".envrc/Makefile", all_paths)
        self.assertNotIn("sub/.envrc/tool.sh", all_paths)
        self.assertGreaterEqual(inv["exclusions"].get("secret_file", 0), 2)
        envrc_cand = make_reference_candidate(provenance=[{"path": ".envrc/Makefile"}])
        envrc_err = self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=json.dumps(envelope(envrc_cand)))
        self.assertIn("excluded", envrc_err.stdout)

        # Kernel file-descriptor offset after reading must not exceed the byte budget or 4 KiB catalog cap.
        read_probe = (
            "import json, os, runpy, sys\n"
            "from io import StringIO\n"
            "from pathlib import Path\n"
            "from unittest.mock import patch\n"
            "cli, repo = Path(sys.argv[1]), Path(sys.argv[2])\n"
            "offsets = {}\n"
            "orig_open = Path.open\n"
            "class Tracked:\n"
            "    def __init__(self, p, h):\n"
            "        self._p, self._h = p, h\n"
            "    def __enter__(self):\n"
            "        self._h.__enter__()\n"
            "        return self\n"
            "    def __exit__(self, *a):\n"
            "        try:\n"
            "            offsets[str(self._p)] = max(offsets.get(str(self._p), 0), os.lseek(self._h.fileno(), 0, os.SEEK_CUR))\n"
            "        except OSError:\n"
            "            pass\n"
            "        return self._h.__exit__(*a)\n"
            "    def __getattr__(self, name):\n"
            "        return getattr(self._h, name)\n"
            "def wrapped_open(self, *a, **kw):\n"
            "    h = orig_open(self, *a, **kw)\n"
            "    if str(self).startswith(str(repo)):\n"
            "        return Tracked(self, h)\n"
            "    return h\n"
            "m = runpy.run_path(str(cli))\n"
            "with patch.object(Path, 'open', wrapped_open), patch.object(sys, 'stdout', StringIO()) as out:\n"
            "    rc = m['cmd_inventory'](m['build_parser']().parse_args(sys.argv[3:]))\n"
            "print(json.dumps({'rc': rc, 'offsets': offsets, 'inv': json.loads(out.getvalue())}))\n"
        )
        budget_repo = self.temp / "budget-repo"
        self.run_command(["git", "init", "-q", budget_repo], self.temp)
        big_script = budget_repo / "scripts/size.sh"
        big_script.parent.mkdir(parents=True)
        big_script.write_text("# " + ("x" * 8192) + "\n", encoding="utf-8")
        self.run_command(["git", "add", "scripts/size.sh"], budget_repo)
        res1 = self.run_command(
            [sys.executable, "-I", "-c", read_probe, str(self.extract_script), str(budget_repo),
             "inventory", "--cwd", str(budget_repo), "--max-bytes", "1"],
            self.nested,
        )
        d1 = json.loads(res1.stdout)
        self.assertEqual(d1["rc"], 0)
        self.assertEqual(d1["offsets"].get(str(big_script.resolve())), 1)

        cat_repo = self.temp / "cat-budget-repo"
        self.run_command(["git", "init", "-q", cat_repo], self.temp)
        cat_pb = cat_repo / ".byte-stack/playbooks/size.md"
        cat_pb.parent.mkdir(parents=True)
        cat_pb.write_text("# Sample\n\nUse when: fixture\n" + ("x" * 8192) + "\n", encoding="utf-8")
        res2 = self.run_command(
            [sys.executable, "-I", "-c", read_probe, str(self.extract_script), str(cat_repo),
             "inventory", "--cwd", str(cat_repo)],
            self.nested,
        )
        d2 = json.loads(res2.stdout)
        self.assertEqual(d2["rc"], 0)
        self.assertEqual(d2["offsets"].get(str(cat_pb.resolve())), 4096)

    def test_r4_provenance_extractor_single_source_of_truth_and_round_trip(self):
        # Package.json with earlier matching property name and escaped quotes in script command.
        self.add_tracked_file(
            "package.json",
            '{\n  "name": "check",\n  "scripts": {\n    "check": "printf \\"hello\\""\n  }\n}\n',
        )
        # Multi-line run: | workflow step (including backslash continuation).
        self.add_tracked_file(
            ".github/workflows/ci.yml",
            "name: CI\non: [push]\njobs:\n  test:\n    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - run: |\n"
            "          pytest -q\n"
            "          ruff check \\\n"
            "            --select E,F .\n",
        )
        # Makefile with modifier, path-prefixed command, and backslash continuation.
        self.add_tracked_file(
            "Makefile",
            "all:\n\t./tools/verify suite\n\t@-go test ./...\n\tgit status \\\n\t  --short\n",
        )
        # TOML with unrelated earlier section.
        self.add_tracked_file("ruff.toml", "[tool.ruff]\n[another]\nline-length = 80\n")
        # JSON hooks config.
        self.add_tracked_file(".claude/settings.json", '{"hooks": {"PreToolUse": [{"command": "node scripts/hook.js"}]}}\n')
        # Shell file with path-prefixed command.
        self.add_tracked_file("scripts/run.sh", "#!/bin/sh\n./tools/verify suite\n", executable=True)

        inv = json.loads(self.extract("inventory").stdout)

        # Round-trip property: EVERY command and key signal emitted by inventory validates at its emitted line.
        round_trip_provs = []
        for files in inv["categories"].values():
            for entry in files:
                for sig in entry["signals"]:
                    if sig["kind"] == "command":
                        prov = {"path": entry["path"], "command": sig["text"], "line": sig["line"]}
                        if "key" in sig:
                            prov["key"] = sig["key"]
                        round_trip_provs.append(prov)
                    elif sig["kind"] == "key":
                        round_trip_provs.append({"path": entry["path"], "key": sig["text"], "line": sig["line"]})
        self.assertGreaterEqual(len(round_trip_provs), 10)
        for i in range(0, len(round_trip_provs), 20):
            batch = round_trip_provs[i : i + 20]
            rt_cand = make_reference_candidate(key=f"rt-{i}.md", provenance=batch)
            rt_res = json.loads(
                self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(envelope(rt_cand))).stdout
            )
            self.assertEqual(rt_res["results"][0]["status"], "create", batch)

        # Check specific package.json line & escaped-quote signal.
        pkg = next(f for f in inv["categories"]["task_runners"] if f["path"] == "package.json")
        check_sig = next(s for s in pkg["signals"] if s["kind"] == "command" and s.get("key") == "scripts.check")
        self.assertEqual(check_sig["line"], 4)
        self.assertEqual(check_sig["text"], 'printf "hello"')
        wrong_pkg_line = make_reference_candidate(
            provenance=[{"path": "package.json", "command": check_sig["text"], "key": "scripts.check", "line": 2}]
        )
        self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=json.dumps(envelope(wrong_pkg_line)))

        # Accepted cases: Make @- modifier, Make backslash continuation (single & multi-line), valid TOML section key.
        for ok_prov in (
            {"path": "Makefile", "line": 3, "command": "go test ./..."},
            {"path": "Makefile", "line": 4, "command": "git status --short"},
            {"path": "Makefile", "line": 4, "command": "git status\n--short"},
            {"path": "ruff.toml", "line": 3, "key": "another.line-length"},
            {"path": "scripts/run.sh", "line": 2, "command": "./tools/verify suite"},
        ):
            with self.subTest(ok_prov=ok_prov):
                c = make_reference_candidate(provenance=[ok_prov])
                r = json.loads(self.extract("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(envelope(c))).stdout)
                self.assertEqual(r["results"][0]["status"], "create")

        # Rejected cases: partial Make/shell command, wrong TOML section, shifted line, key on prose/shell.
        self.add_tracked_file("scripts/shifted.mk", "check:\n\tgit status\n")
        for bad_prov in (
            {"path": "Makefile", "line": 2, "command": "verify suite"},
            {"path": "scripts/run.sh", "line": 2, "command": "verify suite"},
            {"path": "ruff.toml", "line": 3, "key": "tool.ruff.line-length"},
            {"path": "scripts/shifted.mk", "line": 1, "command": "git\nstatus"},
            {"path": "CONTRIBUTING.md", "key": "Contributing"},
            {"path": "scripts/run.sh", "key": "verify"},
        ):
            with self.subTest(bad_prov=bad_prov):
                c = make_reference_candidate(provenance=[bad_prov])
                out = self.extract("write", "--stdin", "--dry-run", "--json", code=1, stdin_text=json.dumps(envelope(c)))
                errs = json.loads(out.stdout)["errors"]
                self.assertTrue(any("path" in e and "line" in e for e in errs), errs)

    def test_r5_catalog_walker_validates_keys_strict_utf8_and_head_truncation(self):
        pb_dir = self.local / "playbooks"
        pb_dir.mkdir(parents=True, exist_ok=True)
        (pb_dir / "bad:name.md").write_text("# Bad\n\nUse when: Verify bad key\n", encoding="utf-8")
        (pb_dir / "invalid.md").write_bytes(b"# Docs\n\nUse when: sample\xff\n")
        # Multi-byte UTF-8 character ('é' = 2 bytes) straddling the 4096-byte boundary after a valid trigger.
        prefix = "# Split\n\nUse when: Valid trigger before split.\n"
        pad = "a" * ((4095 - len(prefix)) % 2)
        filler = "é" * ((4200 - len(prefix) - len(pad)) // 2)
        (pb_dir / "split-utf8.md").write_text(prefix + pad + filler + "\n", encoding="utf-8")
        # Trigger cut at the 4 KiB head boundary.
        (pb_dir / "cut-trigger.md").write_text("# Late\n\nUse when: " + ("z" * 4100) + "\n", encoding="utf-8")

        inv = json.loads(self.extract("inventory").stdout)
        repo_pbs = {e["key"]: e for e in inv["byte_stack"]["playbooks"] if e["origin"] == "repo"}
        self.assertNotIn("bad:name.md", repo_pbs)
        self.assertNotIn("invalid.md", repo_pbs)
        self.assertNotIn("cut-trigger.md", repo_pbs)
        self.assertIn("split-utf8.md", repo_pbs)
        self.assertEqual(repo_pbs["split-utf8.md"]["trigger"], "Valid trigger before split.")
        self.assertTrue(inv["truncated"]["bytes"])
        msgs = [d["message"] for d in inv["diagnostics"]]
        self.assertTrue(any("bad:name.md" in m for m in msgs), msgs)
        self.assertTrue(any("invalid.md" in m or "utf-8" in m.lower() for m in msgs), msgs)
        self.assertTrue(any("cut-trigger.md" in m for m in msgs), msgs)
        self.assertFalse(any("split-utf8.md" in m for m in msgs), msgs)

    def test_r6_r7_r8_link_fallback_late_capture_noop_and_steering_file_conflict(self):
        # R6: fallback to exclusive open when os.link raises EOPNOTSUPP (clean create, intervening file, intervening symlink).
        link_helper = (
            "import errno, os, runpy, sys\n"
            "from pathlib import Path\n"
            "from types import SimpleNamespace\n"
            "from unittest.mock import patch\n"
            "cli, repo, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]\n"
            "m = runpy.run_path(str(cli))\n"
            "g = m['cmd_write'].__globals__\n"
            "target = repo / '.byte-stack/references/link-fb.md'\n"
            "def no_link(src, dst, *a, **kw):\n"
            "    if mode == 'file':\n"
            "        target.write_text('# Intervening human file\\n', encoding='utf-8')\n"
            "    elif mode == 'symlink':\n"
            "        target.symlink_to(repo / 'Makefile')\n"
            "    raise OSError(errno.EOPNOTSUPP, 'no hard links', str(dst))\n"
            "fake_os = SimpleNamespace(**{**vars(os), 'link': no_link})\n"
            "with patch.dict(g, {'os': fake_os}):\n"
            "    sys.exit(m['cmd_write'](m['build_parser']().parse_args(sys.argv[4:])))\n"
        )
        fb_cand = make_reference_candidate(key="link-fb.md")
        fb_target = self.local / "references/link-fb.md"
        r6_ok = self.run_command(
            [sys.executable, "-I", "-c", link_helper, str(self.extract_script), str(self.repo), "clean",
             "write", "--stdin", "--json", "--cwd", str(self.repo), "--approve", fb_cand["id"]],
            self.nested, stdin_text=json.dumps(envelope(fb_cand)),
        )
        self.assertEqual(json.loads(r6_ok.stdout)["results"][0]["status"], "create")
        self.assertEqual(fb_target.read_text(encoding="utf-8"), fb_cand["content"])
        self.assertEqual(list(fb_target.parent.glob(".extract-*")), [])
        fb_target.unlink()

        r6_file = self.run_command(
            [sys.executable, "-I", "-c", link_helper, str(self.extract_script), str(self.repo), "file",
             "write", "--stdin", "--json", "--cwd", str(self.repo), "--approve", fb_cand["id"]],
            self.nested, code=3, stdin_text=json.dumps(envelope(fb_cand)),
        )
        self.assertEqual(json.loads(r6_file.stdout)["results"][0]["status"], "conflict")
        self.assertEqual(fb_target.read_text(encoding="utf-8"), "# Intervening human file\n")
        self.assertEqual(list(fb_target.parent.glob(".extract-*")), [])
        fb_target.unlink()

        r6_sym = self.run_command(
            [sys.executable, "-I", "-c", link_helper, str(self.extract_script), str(self.repo), "symlink",
             "write", "--stdin", "--json", "--cwd", str(self.repo), "--approve", fb_cand["id"]],
            self.nested, code=2, stdin_text=json.dumps(envelope(fb_cand)),
        )
        self.assertIn("symlink", r6_sym.stderr.lower())
        self.assertTrue(fb_target.is_symlink())
        self.assertEqual(list(fb_target.parent.glob(".extract-*")), [])
        fb_target.unlink()

        # R7: late identical capture write reports unchanged and written=False.
        noop_helper = (
            "import json, runpy, sys\n"
            "from pathlib import Path\n"
            "from unittest.mock import patch\n"
            "cli, repo = Path(sys.argv[1]), Path(sys.argv[2])\n"
            "m = runpy.run_path(str(cli))\n"
            "g = m['cmd_write'].__globals__\n"
            "orig = g['_run_capture_subprocess']\n"
            "def interleave(exe, cargs, stdin_text=None):\n"
            "    if cargs[0] == 'write' and '--dry-run' not in cargs:\n"
            "        _, _, cap, _ = g['load_bmode'](None)\n"
            "        payload = json.loads(stdin_text)\n"
            "        t = repo / '.byte-stack' / payload['kind'] / payload['key']\n"
            "        t.parent.mkdir(parents=True, exist_ok=True)\n"
            "        t.write_text(cap.render_playbook(payload), encoding='utf-8')\n"
            "    return orig(exe, cargs, stdin_text=stdin_text)\n"
            "with patch.dict(g, {'_run_capture_subprocess': interleave}):\n"
            "    sys.exit(m['cmd_write'](m['build_parser']().parse_args(sys.argv[3:])))\n"
        )
        late_pb = make_playbook_candidate(key="late-noop.md")
        r7 = self.run_command(
            [sys.executable, "-I", "-c", noop_helper, str(self.extract_script), str(self.repo),
             "write", "--stdin", "--json", "--cwd", str(self.repo), "--approve", late_pb["id"]],
            self.nested, stdin_text=json.dumps(envelope(late_pb)),
        )
        r7_item = json.loads(r7.stdout)["results"][0]
        self.assertEqual(r7_item["status"], "unchanged")
        self.assertFalse(r7_item["written"])
        self.assertEqual(r7_item["diff"], "")

        # R8: candidate that restates steering AND targets a hand-edited file reports both conflicts and splits flags.
        (self.local / "references").mkdir(parents=True, exist_ok=True)
        (self.local / "playbooks").mkdir(parents=True, exist_ok=True)
        hand_ref = self.local / "references/steer-edit.md"
        hand_ref.write_text("# Hand-edited ref\n\nKeep manual notes.\n", encoding="utf-8")
        hand_pb = self.local / "playbooks/steer-edit.md"
        hand_pb.write_text("# Hand-edited pb\n\nUse when: Keep manual playbook.\n", encoding="utf-8")
        steer_ref = make_reference_candidate(
            key="steer-edit.md",
            content="# Steering restate\n\nRestates AGENTS.md.\n",
            provenance=[{"path": "AGENTS.md", "line": 1}],
        )
        steer_pb = make_playbook_candidate(
            key="steer-edit.md",
            title="Steering restate",
            use_when="Follow rules copied from AGENTS.md.",
            provenance=[{"path": "AGENTS.md", "line": 1}],
        )
        raw_r8 = json.dumps(envelope(steer_ref, steer_pb))
        dry_r8 = json.loads(self.extract("write", "--stdin", "--dry-run", "--json", code=3, stdin_text=raw_r8).stdout)
        for item in dry_r8["results"]:
            self.assertEqual(item["status"], "conflict")
            self.assertIn("exists-differs", item["dedupe_flags"])
            self.assertIn("restates-steering", item["dedupe_flags"])
            self.assertIn("steering", item["reason"].lower())
            self.assertIn("--force", item["reason"])
            self.assertIn("--allow-duplicate", item["reason"])
            self.assertIn("Keep manual", item["diff"])

        # Passing only --force OR only --allow-duplicate still conflicts and preserves both hand-edited files.
        for single_flag in ("--force", "--allow-duplicate"):
            self.extract(
                "write", "--stdin", "--json",
                "--approve", steer_ref["id"], "--approve", steer_pb["id"],
                single_flag, steer_ref["id"], single_flag, steer_pb["id"],
                code=3, stdin_text=raw_r8,
            )
            self.assertIn("Keep manual notes.", hand_ref.read_text(encoding="utf-8"))
            self.assertIn("Keep manual playbook.", hand_pb.read_text(encoding="utf-8"))

        # Passing both --force and --allow-duplicate succeeds.
        both_ok = json.loads(
            self.extract(
                "write", "--stdin", "--json",
                "--approve", steer_ref["id"], "--approve", steer_pb["id"],
                "--force", steer_ref["id"], "--force", steer_pb["id"],
                "--allow-duplicate", steer_ref["id"], "--allow-duplicate", steer_pb["id"],
                stdin_text=raw_r8,
            ).stdout
        )
        self.assertTrue(all(r["status"] == "force-overwrite" and r["written"] for r in both_ok["results"]))


    def test_home_paths_under_other_roots_and_truncated_signal_citation(self):
        # The home-path guard is the same for all four kinds, and it covers a home
        # directory under another root (/var/home, /mnt/c/Users, /export/home).
        literals = ("/var/home/alice/notes/", "/mnt/c/Users/alice/x", "/export/home/alice", "C:\\Users\\")
        for literal in literals:
            cases = [
                ("playbook", make_playbook_candidate(steps=["Inspect " + literal])),
                ("workflow", make_workflow_candidate(steps=["Inspect " + literal])),
                ("reference", make_reference_candidate(content="# Notes\n\nInspect " + literal + "\n")),
                ("script", make_script_candidate(content="#!/bin/sh\nls " + literal + "\n")),
            ]
            for label, cand in cases:
                with self.subTest(literal=literal, kind=label):
                    out = self.extract("write", "--stdin", "--dry-run", code=1, stdin_text=json.dumps(envelope(cand)))
                    self.assertIn("machine-local", out.stderr + out.stdout)
        self.assertFalse(self.local.exists())

        # The scan drops a signal that holds such a path, and keeps a URL path and
        # a repo-relative path that only look similar.
        self.add_tracked_file(
            "docs/directives/paths.md",
            "# Backups live in /var/home/alice/backups\n\n## See https://example.com/home/page for details\n\n"
            "## Layout docs/home/alice/readme\n",
        )
        long_cmd = "docker run --rm " + " ".join("--env VAR%d=value%d" % (i, i) for i in range(20)) + " image:tag check"
        self.add_tracked_file("Makefile", ".PHONY: test lint\ntest:\n\tpython3 -m unittest\nlong:\n\t" + long_cmd + "\n")
        inv_out = self.extract("inventory").stdout
        self.assertNotIn("/var/home/alice", inv_out)
        self.assertIn("https://example.com/home/page", inv_out)
        self.assertIn("docs/home/alice/readme", inv_out)

        # A command the scan prints shortened can be cited exactly as printed.
        inv = json.loads(inv_out)
        makefile = next(f for f in inv["categories"]["task_runners"] if f["path"] == "Makefile")
        shortened = next(s for s in makefile["signals"] if s["kind"] == "command" and s["text"].endswith("..."))
        self.assertLess(len(shortened["text"]), len(long_cmd))
        cited = make_reference_candidate(provenance=[{"path": "Makefile", "line": shortened["line"], "command": shortened["text"]}])
        self.extract("write", "--stdin", "--dry-run", stdin_text=json.dumps(envelope(cited)))
        wrong = make_reference_candidate(provenance=[{"path": "Makefile", "line": shortened["line"], "command": "docker stop " + shortened["text"][12:]}])
        out = self.extract("write", "--stdin", "--dry-run", code=1, stdin_text=json.dumps(envelope(wrong)))
        self.assertIn("command not found", out.stderr + out.stdout)


    def test_argument_errors_quoted_root_deep_home_paths_and_web_urls(self):
        # A usage error does not echo a credential-shaped argument.
        token = "ghp_" + "A" * 24
        for args in (("--max-bytes", token), ("--max=" + token,), ("--pretty=" + token,), (token,)):
            with self.subTest(args=args[0].replace(token, "TOKEN")):
                out = self.extract("inventory", *args, code=2)
                self.assertNotIn(token, out.stderr + out.stdout)
                self.assertIn("error", out.stderr)

        # The repository root is redacted inside typographic quotes too, and a home
        # directory is caught at any depth of an absolute path.
        deep = "/mnt/org/teams/region/hosts/userdata/home/sample"
        self.add_tracked_file(
            "docs/directives/places.md",
            "# Checkout lives at “" + str(self.repo) + "” today\n\n## Shared files in " + deep + "\n\n"
            "## Guide at https://example.test/home/docs/index\n",
        )
        inv_out = self.extract("inventory").stdout
        self.assertNotIn(str(self.repo), inv_out)
        self.assertNotIn(deep, inv_out)
        self.assertIn("https://example.test/home/docs/index", inv_out)
        for label, cand in (
            ("reference", make_reference_candidate(content="# Notes\n\nShared files in " + deep + "\n")),
            ("script", make_script_candidate(content="#!/bin/sh\nls " + deep + "\n")),
            ("playbook", make_playbook_candidate(steps=["List " + deep])),
        ):
            with self.subTest(kind=label):
                out = self.extract("write", "--stdin", "--dry-run", code=1, stdin_text=json.dumps(envelope(cand)))
                self.assertIn("machine-local", out.stderr + out.stdout)

        # A web URL whose path has a home segment is ordinary documentation.
        linked = make_reference_candidate(content="# Notes\n\nRead https://example.test/home/docs/index first.\n")
        self.extract("write", "--stdin", "--dry-run", stdin_text=json.dumps(envelope(linked)))
        self.assertFalse(self.local.exists())

    def test_provenance_round_trip_for_continuations_dotted_scripts_just_and_toml_comments(self):
        self.add_tracked_file("CONTRIBUTING.md", "# Contributing\n\n```sh\ngit status \\\n  --short\nmake test\n```\n")
        self.add_tracked_file(
            "package.json",
            '{\n  "name": "fixture",\n  "scripts": {\n    "lint.fix": "eslint --fix .",\n    "test": "node --test"\n  }\n}\n',
        )
        self.add_tracked_file("Justfile", "test:\n    cargo test --all\n")
        self.add_tracked_file("ruff.toml", 'line-length = 100\n\n[format] # style rules\nquote-style = "double"\n')
        inv = json.loads(self.extract("inventory").stdout)
        files = {f["path"]: f for bucket in inv["categories"].values() for f in bucket}

        def signals(path, kind):
            return [s for s in files[path]["signals"] if s["kind"] == kind]

        # One joined command for a fenced continuation, at its first line.
        self.assertIn({"kind": "command", "line": 4, "text": "git status --short"}, signals("CONTRIBUTING.md", "command"))
        self.assertNotIn("--short", [s["text"] for s in signals("CONTRIBUTING.md", "command")])
        self.assertIn("scripts.lint.fix", [s.get("key") for s in signals("package.json", "command")])
        self.assertIn("cargo test --all", [s["text"] for s in signals("Justfile", "command")])
        self.assertIn("format.quote-style", [s["text"] for s in signals("ruff.toml", "key")])

        # Every command and key the scan prints can be cited at its line.
        for path in ("CONTRIBUTING.md", "package.json", "Justfile", "ruff.toml"):
            for sig in files[path]["signals"]:
                if sig["kind"] not in ("command", "key"):
                    continue
                prov = {"path": path, "line": sig["line"], sig["kind"]: sig["text"]}
                if sig["kind"] == "command" and "key" in sig:
                    prov["key"] = sig["key"]
                with self.subTest(path=path, signal=sig["text"]):
                    self.extract("write", "--stdin", "--dry-run", stdin_text=json.dumps(envelope(make_reference_candidate(provenance=[prov]))))

        # A key under a commented section header is not accepted without its section.
        bare = make_reference_candidate(provenance=[{"path": "ruff.toml", "key": "quote-style"}])
        out = self.extract("write", "--stdin", "--dry-run", code=1, stdin_text=json.dumps(envelope(bare)))
        self.assertIn("key not found", out.stderr + out.stdout)

        # A package.json the scan cannot parse never yields the bare key "scripts".
        self.add_tracked_file("package.json", '{\n  // comment\n  "name": "fixture",\n  "scripts": {\n    "test": "node --test"\n  }\n}\n')
        inv = json.loads(self.extract("inventory").stdout)
        package = next(f for f in inv["categories"]["task_runners"] if f["path"] == "package.json")
        self.assertNotIn("scripts", [s["text"] for s in package["signals"] if s["kind"] == "key"])

    def test_catalog_head_only_entries_are_flagged_and_reference_triggers_deduplicate(self):
        # An asset larger than the 4 KiB head is listed, and marked as read in part.
        body = "# Long\n\nUse when: Inspect a long asset.\n\n" + ("Filler line for the long asset.\n" * 200)
        short = "# Short\n\nUse when: Inspect a short asset.\n\nBody.\n"
        (self.local / "playbooks").mkdir(parents=True)
        (self.local / "playbooks/long.md").write_text(body, encoding="utf-8")
        (self.local / "playbooks/short.md").write_text(short, encoding="utf-8")
        inv = json.loads(self.extract("inventory").stdout)
        entries = {e["key"]: e for e in inv["byte_stack"]["playbooks"] if e["origin"] == "repo"}
        self.assertTrue(entries["long.md"].get("truncated"))
        self.assertNotIn("truncated", entries["short.md"])

        # Two references with different titles and the same trigger are duplicates,
        # within one batch and against a reference already in the repository.
        def ref(key, title):
            return make_reference_candidate(key=key, content="# " + title + "\n\nUse when: Verify dependency graph.\n\nBody of " + title + ".\n")

        out = self.extract("write", "--stdin", "--dry-run", "--json", code=3, stdin_text=json.dumps(envelope(ref("graph-one.md", "Graph one"), ref("graph-two.md", "Graph two"))))
        results = {r["id"]: r for r in json.loads(out.stdout)["results"]}
        self.assertEqual(results["references/graph-one.md"]["dedupe_flags"], [])
        self.assertIn("duplicates-catalog", results["references/graph-two.md"]["dedupe_flags"])
        (self.local / "references").mkdir()
        (self.local / "references/existing.md").write_text("# Existing\n\nUse when: Verify dependency graph.\n\nOld body.\n", encoding="utf-8")
        out = self.extract("write", "--stdin", "--dry-run", "--json", code=3, stdin_text=json.dumps(envelope(ref("graph-one.md", "Graph one"))))
        self.assertIn("duplicates-catalog", json.loads(out.stdout)["results"][0]["dedupe_flags"])


if __name__ == "__main__":
    unittest.main()
