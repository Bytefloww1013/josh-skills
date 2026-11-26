#!/usr/bin/env python3
"""Tests for pre_pr_reminder.py. Standard library only."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "pre_pr_reminder.py"
ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], env=ENV, check=True, capture_output=True, text=True)


def make_branch(root, files):
    """A repo on main with one commit, then a branch that adds `files`."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-b", "main")
    (root / "README.md").write_text("hi\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "init")
    git(root, "checkout", "-b", "doc/add-issue1-demo")
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "change")


def run(command, cwd):
    payload = json.dumps({"tool_input": {"command": command}, "cwd": str(cwd)})
    out = subprocess.run([sys.executable, str(SCRIPT)], input=payload, capture_output=True, text=True, check=True)
    return out.stdout.strip()


class PrePrReminderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_other_commands_get_nothing(self):
        self.assertEqual(run("gh pr list", self.root), "")

    def test_docs_only_branch_skips_reminder(self):
        repo = self.root / "repo"
        make_branch(repo, ["GLOSSARY.md", "docs/guide.mdx", "notes.txt"])
        self.assertEqual(run("gh pr create --base main --title t --body b", repo), "")

    def test_code_change_gets_reminder(self):
        repo = self.root / "repo"
        make_branch(repo, ["GLOSSARY.md", "src/app.py"])
        self.assertIn("pr-erosion-check", run("gh pr create --title t --body b", repo))

    def test_code_renamed_to_doc_gets_reminder(self):
        repo = self.root / "repo"
        make_branch(repo, ["app.py"])
        git(repo, "branch", "before-rename")
        git(repo, "mv", "app.py", "app.md")
        git(repo, "commit", "-m", "rename")
        self.assertIn("pr-erosion-check", run("gh pr create --base before-rename", repo))

    def test_cd_in_command_picks_the_repo(self):
        repo = self.root / "repo"
        make_branch(repo, ["docs/a.md"])
        other = self.root / "elsewhere"
        other.mkdir()
        self.assertEqual(run(f"cd {repo} && gh pr create --base main --title t", other), "")

    def test_unknown_repo_or_base_gets_reminder(self):
        self.assertIn("pr-erosion-check", run("gh pr create --title t", self.root))
        repo = self.root / "repo"
        make_branch(repo, ["docs/a.md"])
        self.assertIn("pr-erosion-check", run("gh pr create --base nope --title t", repo))


if __name__ == "__main__":
    unittest.main()
