#!/usr/bin/env python3
"""Tests for pre_pr_reminder.py (Claude Code and Antigravity payloads). Standard library only."""
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


def invoke(payload_text, proc_cwd=None):
    out = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=payload_text,
        cwd=str(proc_cwd) if proc_cwd is not None else None,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def run_claude(command, cwd):
    payload = json.dumps({"tool_input": {"command": command}, "cwd": str(cwd)})
    return invoke(payload)


def run_antigravity(command, cwd=None, *, arg_key="CommandLine", workspace_paths=None, proc_cwd=None):
    payload = {
        "hookEventName": "PreToolUse",
        "toolCall": {
            "id": "toolu_01",
            "name": "run_command",
            "args": {arg_key: command},
        },
    }
    if cwd is not None:
        payload["cwd"] = str(cwd)
    if workspace_paths is not None:
        payload["workspacePaths"] = [str(p) for p in workspace_paths]
    return invoke(json.dumps(payload), proc_cwd=proc_cwd)


class PrePrReminderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def assert_skipped(self, harness, raw):
        if harness == "claude":
            self.assertEqual(raw, "")
        else:
            parsed = json.loads(raw)
            self.assertEqual(parsed, {"decision": "allow"})

    def assert_reminded(self, harness, raw):
        parsed = json.loads(raw)
        if harness == "claude":
            hook_out = parsed.get("hookSpecificOutput") or {}
            self.assertEqual(hook_out.get("hookEventName"), "PreToolUse")
            self.assertIn("pr-erosion-check", hook_out.get("additionalContext", ""))
        else:
            self.assertEqual(parsed.get("decision"), "allow")
            self.assertIn("pr-erosion-check", parsed.get("reason", ""))

    def run_for_both(self, command, cwd):
        return (
            ("claude", run_claude(command, cwd)),
            ("antigravity", run_antigravity(command, cwd)),
        )

    def test_other_commands_get_no_reminder(self):
        for harness, raw in self.run_for_both("gh pr list", self.root):
            with self.subTest(harness=harness):
                self.assert_skipped(harness, raw)

    def test_docs_only_branch_skips_reminder(self):
        repo = self.root / "repo"
        make_branch(repo, ["GLOSSARY.md", "docs/guide.mdx", "notes.txt"])
        for harness, raw in self.run_for_both("gh pr create --base main --title t --body b", repo):
            with self.subTest(harness=harness):
                self.assert_skipped(harness, raw)

    def test_code_change_gets_reminder(self):
        repo = self.root / "repo"
        make_branch(repo, ["GLOSSARY.md", "src/app.py"])
        for harness, raw in self.run_for_both("gh pr create --title t --body b", repo):
            with self.subTest(harness=harness):
                self.assert_reminded(harness, raw)

    def test_code_renamed_to_doc_gets_reminder(self):
        repo = self.root / "repo"
        make_branch(repo, ["app.py"])
        git(repo, "branch", "before-rename")
        git(repo, "mv", "app.py", "app.md")
        git(repo, "commit", "-m", "rename")
        for harness, raw in self.run_for_both("gh pr create --base before-rename", repo):
            with self.subTest(harness=harness):
                self.assert_reminded(harness, raw)

    def test_cd_in_command_picks_the_repo(self):
        repo = self.root / "repo"
        make_branch(repo, ["docs/a.md"])
        other = self.root / "elsewhere"
        other.mkdir()
        for harness, raw in self.run_for_both(f"cd {repo} && gh pr create --base main --title t", other):
            with self.subTest(harness=harness):
                self.assert_skipped(harness, raw)

    def test_unknown_repo_or_base_gets_reminder(self):
        for harness, raw in self.run_for_both("gh pr create --title t", self.root):
            with self.subTest(case="non-git", harness=harness):
                self.assert_reminded(harness, raw)
        repo = self.root / "repo"
        make_branch(repo, ["docs/a.md"])
        for harness, raw in self.run_for_both("gh pr create --base nope --title t", repo):
            with self.subTest(case="unknown-base", harness=harness):
                self.assert_reminded(harness, raw)

    def test_antigravity_lowercase_command_arg(self):
        docs_repo = self.root / "docs-repo"
        make_branch(docs_repo, ["docs/guide.md"])
        self.assert_skipped("antigravity", run_antigravity("gh pr create --base main", docs_repo, arg_key="command"))

        code_repo = self.root / "code-repo"
        make_branch(code_repo, ["src/main.py"])
        self.assert_reminded("antigravity", run_antigravity("gh pr create --base main", code_repo, arg_key="command"))

    def test_antigravity_workspace_paths_fallback_when_cwd_omitted(self):
        docs_repo = self.root / "ws-docs"
        make_branch(docs_repo, ["docs/guide.md"])
        other = self.root / "plugin-dir"
        other.mkdir()
        raw = run_antigravity("gh pr create --base main", cwd=None, workspace_paths=[docs_repo], proc_cwd=other)
        self.assert_skipped("antigravity", raw)

        code_repo = self.root / "ws-code"
        make_branch(code_repo, ["src/app.py"])
        raw = run_antigravity("gh pr create --base main", cwd=None, workspace_paths=[code_repo], proc_cwd=other)
        self.assert_reminded("antigravity", raw)

    def test_extra_spaces_in_the_command_still_get_the_reminder(self):
        repo = self.root / "repo"
        make_branch(repo, ["src/app.py"])
        for harness, raw in self.run_for_both("gh  pr   create --base main --title t", repo):
            with self.subTest(harness=harness):
                self.assert_reminded(harness, raw)

    def test_cd_as_an_option_value_is_not_a_directory_change(self):
        repo = self.root / "repo"
        make_branch(repo, ["docs/a.md"])
        for harness, raw in self.run_for_both("gh pr create --base main --title cd --body example", repo):
            with self.subTest(harness=harness):
                self.assert_skipped(harness, raw)

    def test_cd_before_a_semicolon_picks_the_repo(self):
        repo = self.root / "repo"
        make_branch(repo, ["docs/a.md"])
        other = self.root / "elsewhere"
        other.mkdir()
        for harness, raw in self.run_for_both(f"cd {repo}; gh pr create --base main --title t", other):
            with self.subTest(harness=harness):
                self.assert_skipped(harness, raw)

    def test_unknown_default_branch_gets_reminder(self):
        # No --base and no origin/HEAD: the default branch is not known, so local `main` is not taken for it.
        repo = self.root / "repo"
        make_branch(repo, ["docs/a.md"])
        for harness, raw in self.run_for_both("gh pr create --title t", repo):
            with self.subTest(harness=harness):
                self.assert_reminded(harness, raw)

    def test_default_branch_comes_from_origin_head(self):
        repo = self.root / "repo"
        make_branch(repo, ["docs/a.md"])
        git(repo, "update-ref", "refs/remotes/origin/main", "main")
        git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        for harness, raw in self.run_for_both("gh pr create --title t", repo):
            with self.subTest(harness=harness):
                self.assert_skipped(harness, raw)

    def test_nul_byte_in_the_folder_still_answers(self):
        payload = {"toolCall": {"args": {"CommandLine": "gh pr create", "Cwd": "\u0000"}}}
        self.assert_reminded("antigravity", invoke(json.dumps(payload)))
        payload = {"tool_input": {"command": "gh pr create"}, "cwd": "\u0000"}
        self.assert_reminded("claude", invoke(json.dumps(payload)))

    def test_malformed_or_non_object_json_outputs_nothing(self):
        self.assertEqual(invoke("not json"), "")
        self.assertEqual(invoke("[]"), "")
        self.assertEqual(invoke("null"), "")


if __name__ == "__main__":
    unittest.main()
