#!/usr/bin/env python3
"""Tests for erosion_scan.py. Standard library only."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "erosion_scan.py"


def git(repo, *args):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(["git", "-C", str(repo), *args], env=env, check=True, capture_output=True, text=True)


def make_repo(root, adr_rel="docs/adr", branch="feature/issue42-demo"):
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-b", "main")
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
    if adr_rel:
        adr_dir = root / adr_rel
        adr_dir.mkdir(parents=True)
        (adr_dir / "0001-demo.md").write_text(
            "# 1. Demo decision\n\nStatus: Accepted\nScope: src/**\n\n## Decision\n\nKeep greetings simple.\n",
            encoding="utf-8",
        )
    git(root, "add", ".")
    git(root, "commit", "-m", "base commit")

    git(root, "checkout", "-b", branch)
    (root / "src" / "app.py").write_text(
        "def greet():\n    try:\n        return 'hello'\n    except Exception:\n        pass\n",
        encoding="utf-8",
    )
    git(root, "add", ".")
    git(root, "commit", "-m", "branch change")
    return root


class ErosionScanTests(unittest.TestCase):
    def test_help_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = subprocess.run(
                [sys.executable, str(SCRIPT), "--help"],
                cwd=tmp,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("erosion_scan.py", res.stdout)
            self.assertEqual(os.listdir(tmp), [])

    def test_text_and_json_output_with_adr(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp) / "repo")
            body = Path(tmp) / "pr-body.md"
            body.write_text("Closes #99\n", encoding="utf-8")

            text_res = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo", str(repo), "--base", "main", "--body", str(body), "--issue", "100"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(text_res.returncode, 0, text_res.stderr)
            self.assertIn("== diff_scan\n", text_res.stdout)
            self.assertIn("\n== scope_check\n", text_res.stdout)
            self.assertIn("\n== adr_match\n", text_res.stdout)
            self.assertIn("#42", text_res.stdout)
            self.assertIn("#99", text_res.stdout)
            self.assertIn("#100", text_res.stdout)
            self.assertIn("1. Demo decision", text_res.stdout)

            json_res = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo", str(repo), "--base", "main", "--body", str(body), "--issue", "100", "--json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(json_res.returncode, 0, json_res.stderr)
            data = json.loads(json_res.stdout)
            self.assertEqual(set(data.keys()), {"diff_scan", "scope_check", "adr_match"})
            self.assertEqual(data["diff_scan"]["size"]["files"], 1)
            self.assertEqual(data["scope_check"]["linked_issues"], ["#42", "#99", "#100"])
            self.assertEqual(len(data["adr_match"]["matching"]), 1)

    def test_default_adr_dir_fallback_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_dec = make_repo(Path(tmp) / "repo-dec", adr_rel="docs/decisions")
            res_dec = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo", str(repo_dec), "--json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res_dec.returncode, 0, res_dec.stderr)
            self.assertEqual(len(json.loads(res_dec.stdout)["adr_match"]["matching"]), 1)

            repo_none = make_repo(Path(tmp) / "repo-none", adr_rel=None)
            res_none = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo", str(repo_none), "--json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res_none.returncode, 0, res_none.stderr)
            parsed = json.loads(res_none.stdout)
            self.assertEqual(set(parsed.keys()), {"diff_scan", "scope_check", "adr_match"})
            self.assertIn("skipped", parsed["adr_match"])

    def test_explicit_missing_adr_dir_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp) / "repo")
            res = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo", str(repo), "--adr-dir", "does/not/exist"],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("adr_match.py", res.stderr)


if __name__ == "__main__":
    unittest.main()
