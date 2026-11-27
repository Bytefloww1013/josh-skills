"""Run from any directory with python3 tests/test_byte_stack_assets.py."""
import concurrent.futures
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "plugins/byte-stack/skills"
INIT = SKILLS / "init/scripts/init.py"


class AssetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.repo = self.temp / "target with spaces"
        self.run_command(["git", "init", "-q", self.repo], self.temp)
        self.nested = self.repo / "nested"
        self.nested.mkdir()
        self.local = self.repo / ".byte-stack"
        # A selective skill installation cannot reach other plugin files.
        self.bundle = self.temp / "skills/bmode"
        shutil.copytree(SKILLS / "bmode", self.bundle)
        self.resolver = self.bundle / "scripts/assets.py"

    def run_command(self, args, cwd, code=0):
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stderr + result.stdout)
        return result.stdout if code == 0 else result.stderr

    def assets(self, *args, cwd=None, code=0):
        return self.run_command([sys.executable, "-I", self.resolver, *args], cwd or self.nested, code)

    def snapshot(self):
        return {p.relative_to(self.local): (p.stat().st_mode, p.stat().st_mtime_ns,
                                            p.read_bytes() if p.is_file() else None)
                for p in self.local.rglob("*")}

    def test_init_preserves_user_files_and_completes_partial_tree(self):
        owned = self.local / "scripts/check.sh"
        owned.parent.mkdir(parents=True)
        owned.write_text("#!/bin/sh\nexit 0\n")
        owned.chmod(0o751)
        before = self.snapshot()[owned.relative_to(self.local)]
        self.run_command([sys.executable, INIT], self.nested)
        self.assertEqual({p.name for p in self.local.iterdir()},
                         {"scripts", "playbooks", "references", "workflows"})
        after = self.snapshot()
        self.assertEqual(before, after[owned.relative_to(self.local)])
        self.assertIn("Already initialized", self.run_command([sys.executable, INIT], self.repo))
        self.assertEqual(after, self.snapshot())

    def test_init_conflict_and_concurrent_retry(self):
        self.local.mkdir()
        (self.local / "scripts").symlink_to(self.temp, target_is_directory=True)
        self.run_command([sys.executable, INIT], self.repo, 1)
        self.assertEqual([p.name for p in self.local.iterdir()], ["scripts"])
        (self.local / "scripts").unlink()
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda _: self.run_command([sys.executable, INIT], self.repo), range(2)))
        self.assertEqual(len(list(self.local.glob("*/.gitkeep"))), 4)

    def test_local_bundle_custom_and_malformed(self):
        key = "investigation.md"
        self.assertIn("bundled\t", self.assets("resolve", "playbooks", key))
        self.assertFalse(self.local.exists())
        d = self.local / "playbooks"
        d.mkdir(parents=True)
        (d / key).write_text("Follow the local instructions.")
        (d / "custom.md").write_text("Use when: verify custom selection\n")
        self.assertEqual(self.assets("resolve", "playbooks", key).strip(), f"repo\t{d / key}")
        self.assertIn("custom.md\tverify custom selection", self.assets("list-playbooks"))
        self.assertIn("investigation.md\tAnswer a read-only", self.assets("list-playbooks"))
        self.assertIn("custom.md", self.assets("resolve", "playbooks", "missing.md", code=1))
        (d / key).write_text("")
        self.assertIn("empty asset", self.assets("resolve", "playbooks", key, code=2))

    def test_frontmatter_triggers_and_malformed_frontmatter(self):
        d = self.local / "playbooks"
        d.mkdir(parents=True)
        fm_path = d / "release-notes.md"
        fm_path.write_text(
            '---\nschema-version: 1\nuse-when: "Prepare release notes: tagged builds"\n---\n\n# Release notes\n\nCheck tags.\n',
            encoding="utf-8",
        )
        self.assertEqual(self.assets("resolve", "playbooks", "release-notes.md").strip(), f"repo\t{fm_path}")
        self.assertIn("release-notes.md\tPrepare release notes: tagged builds", self.assets("list-playbooks"))

        fm_path.write_text("---\nuse-when: Unterminated\n# Body\n", encoding="utf-8")
        self.assertIn("unterminated frontmatter", self.assets("resolve", "playbooks", "release-notes.md", code=2))

        fm_path.write_text("---\nuse-when: No body\n---\n   \n", encoding="utf-8")
        self.assertIn("empty asset", self.assets("resolve", "playbooks", "release-notes.md", code=2))

        fm_path.write_text("---\nuse-when: One\nuse-when: Two\n---\n\n# Title\n", encoding="utf-8")
        self.assertIn("duplicate frontmatter key", self.assets("resolve", "playbooks", "release-notes.md", code=2))

        fm_path.write_text(
            "---\nuse-when: Trigger from frontmatter\n---\n\nUse when: Trigger from body\n\n# Body\n",
            encoding="utf-8",
        )
        self.assertIn("conflicting trigger", self.assets("resolve", "playbooks", "release-notes.md", code=2))

    def test_script_workflow_helper_and_unsafe_keys(self):
        self.run_command([sys.executable, INIT], self.nested)
        for kind, key in [("scripts", "check.py"), ("workflows", "release.md")]:
            path = self.local / kind / key
            path.write_text("raise RuntimeError('probe was executed')")
            self.assertIn(str(path), self.assets("resolve", kind, key))
        owner = SKILLS / "how"
        args = ["--owner", owner, "resolve", "references", "explorer-prompt.md"]
        self.assertIn("bundled\t", self.assets(*args))
        override = self.local / "references/how/explorer-prompt.md"
        override.parent.mkdir()
        override.write_text("Use this prompt.")
        self.assertIn(str(override), self.assets(*args))
        override.unlink()
        override.symlink_to(self.temp / "outside")
        self.assertIn("symlink", self.assets(*args, code=2))
        for key in ["../outside.md", "/outside.md", "x/../outside.md"]:
            self.assertIn("invalid asset key", self.assets("resolve", "references", key, code=2))

    def test_worktree_and_outside_git(self):
        self.run_command(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                          "commit", "-qm", "fixture", "--allow-empty"], self.repo)
        linked = self.temp / "linked"
        self.run_command(["git", "worktree", "add", "-q", "--detach", linked], self.repo)
        path = self.local / "playbooks/investigation.md"
        path.parent.mkdir(parents=True)
        path.write_text("Main checkout only.")
        self.assertIn("bundled\t", self.assets("resolve", "playbooks", path.name, cwd=linked))
        self.assertIn("bundled\t", self.assets("resolve", "playbooks", path.name, cwd=self.temp))
        self.assertIn("Git worktree", self.run_command([sys.executable, INIT], self.temp, 1))
        self.assertFalse((self.temp / ".byte-stack").exists())

    def test_delegated_brief_and_report_use_same_local_template(self):
        briefs = self.bundle / "references/briefs"
        local = self.local / "references/briefs"
        local.mkdir(parents=True)
        (local / "reviewer.md").write_text(
            "# Review {{TASK_ID}}\n{{SHARED_RULES}}\n"
            "````markdown\n**Verdict:** PASS | REVISE\n## Local evidence\n\n````\n")
        data = self.temp / "values.json"
        data.write_text(json.dumps({"TASK_ID": "fixture", "RUN_DIR": str(self.temp)}))
        output = self.run_command([sys.executable, "-I", briefs / "fill-brief.py", "reviewer",
                                   "--values", data], self.nested)
        self.assertIn("# Review fixture", output)
        self.assertIn("## Local evidence", output)
        report = self.temp / "report.md"
        report.write_text("**Verdict:** PASS\n## Local evidence\nReviewed local override.")
        self.assertIn("PASS", self.run_command(
            [sys.executable, "-I", briefs / "check-report.py", "reviewer", report], self.nested))

    def test_bundled_reviewer_brief_applies_the_repo_coding_standards(self):
        brief = (SKILLS / "bmode/references/briefs/reviewer.md").read_text(encoding="utf-8")
        rules = brief.split("## Reviewer rules", 1)[1].split("\n## ", 1)[0]
        numbers = [int(line.split(".", 1)[0]) for line in rules.splitlines() if line[:1].isdigit()]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))
        self.assertIn("CODING_STANDARDS.md", rules)
        data = self.temp / "values.json"
        data.write_text(json.dumps({"TASK_ID": "fixture", "RUN_DIR": str(self.temp), "REPO_ROOT": str(self.repo), "BASE": "base",
                                     "HEAD": "head", "GOAL": "goal", "ISSUE": "none", "EXTRA_CONSTRAINTS": "none"}))
        output = self.run_command([sys.executable, "-I", self.bundle / "references/briefs/fill-brief.py", "reviewer",
                                   "--values", data], self.nested)
        self.assertIn("CODING_STANDARDS.md", output)
        self.assertNotIn("{{", output.split("## Report", 1)[0])


if __name__ == "__main__":
    unittest.main()
