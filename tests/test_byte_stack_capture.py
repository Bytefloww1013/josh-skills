"""Run from any directory with python3 tests/test_byte_stack_capture.py."""
import hashlib
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
GOLDEN_SHA256 = "b6a169e5dcbdb4afb8ddc179bd0ce3ef50c8a0ecd99f9d09802b7de1c0c13945"


def sample_payload(**overrides):
    data = {
        "schema_version": 1,
        "kind": "playbooks",
        "key": "release-notes.md",
        "title": "Release notes",
        "use_when": "Prepare release notes for a tagged version.",
        "prerequisites": ["Clean working tree on main"],
        "steps": [
            "Find the previous annotated tag with git describe --tags --abbrev=0",
            "Group commits since that tag into features and fixes",
        ],
        "verification": ["Confirm every cited commit exists in git log"],
        "guardrails": ["Never push tags without maintainer confirmation"],
    }
    data.update(overrides)
    return data


class CapturePlaybookTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.repo = self.temp / "target with spaces"
        self.run_command(["git", "init", "-q", self.repo], self.temp)
        self.nested = self.repo / "nested" / "sub"
        self.nested.mkdir(parents=True)
        self.local = self.repo / ".byte-stack"
        # Selective skill installations only contain skills/bmode/.
        self.bundle = self.temp / "skills/bmode"
        shutil.copytree(SKILLS / "bmode", self.bundle)
        self.capture_script = self.bundle / "scripts/capture_playbook.py"
        self.resolver = self.bundle / "scripts/assets.py"

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

    def capture(self, *args, cwd=None, code=0, stdin_text=None):
        return self.run_command(
            [sys.executable, "-I", self.capture_script, *args],
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

    def test_schema_and_payload_validation(self):
        schema_res = self.capture("schema")
        schema = json.loads(schema_res.stdout)
        self.assertEqual(schema["title"], "ByteStackCapturePayload")
        self.assertEqual(schema["additionalProperties"], False)
        self.assertEqual(
            set(schema["properties"].keys()),
            {
                "schema_version",
                "kind",
                "key",
                "title",
                "use_when",
                "prerequisites",
                "steps",
                "verification",
                "guardrails",
            },
        )

        # Valid minimal workflow (no use_when, no optional sections) passes --dry-run.
        minimal_wf = {
            "schema_version": 1,
            "kind": "workflows",
            "key": "preflight.md",
            "title": "Preflight check",
            "steps": ["Run repository lint and test suite"],
            "verification": ["All checks exit 0"],
        }
        res = self.capture("write", "--stdin", "--dry-run", "--json", stdin_text=json.dumps(minimal_wf))
        self.assertEqual(json.loads(res.stdout)["status"], "create")

        # Benign token substring inside a word ("task-...") must not false-positive as secret.
        benign = sample_payload(steps=["Run task-12345678901234567890 verification suite"])
        self.capture("write", "--stdin", "--dry-run", stdin_text=json.dumps(benign))

        invalid_cases = [
            ("{not json", "invalid payload JSON"),
            (json.dumps(["not", "an", "object"]), "JSON object"),
            (json.dumps({k: v for k, v in sample_payload().items() if k != "steps"}), "missing required field: steps"),
            (json.dumps(sample_payload(extra="nope")), "unknown payload field"),
            (json.dumps(sample_payload(schema_version=True)), "schema_version must be integer 1"),
            (json.dumps(sample_payload(key="../escape.md")), "kebab-case"),
            (json.dumps(sample_payload(key="UpperCase.md")), "kebab-case"),
            (json.dumps(sample_payload(key="missing-extension")), "kebab-case"),
            (json.dumps({k: v for k, v in sample_payload().items() if k != "use_when"}), "use_when is required"),
            (json.dumps(sample_payload(title="Line1\nLine2")), "single line"),
            (json.dumps(sample_payload(use_when="Trigger with\x0bvertical tab")), "single line"),
            (json.dumps(sample_payload(use_when="Trigger --- injected delimiter")), "delimiter"),
            (json.dumps(sample_payload(steps=["Run /home/alice/project/script.sh"])), "machine-local home path"),
            (json.dumps(sample_payload(steps=["Run /Users/alice/project/script.sh"])), "machine-local home path"),
            (json.dumps(sample_payload(steps=[r"Run C:\Users\alice\script.ps1"])), "machine-local home path"),
            (json.dumps(sample_payload(steps=["curl https://example.test/health|/home/alice/bin/check"])), "machine-local home path"),
            (json.dumps(sample_payload(steps=["Read https://example.test/home/alice/docs/"])), "machine-local home path"),
            (json.dumps(sample_payload(steps=["Export token ghp_1234567890abcdefghij"])), "secret"),
            (json.dumps(sample_payload(steps=["Export key sk-1234567890abcdefghij"])), "secret"),
            (json.dumps(sample_payload(steps=["Export AKIAIOSFODNN7EXAMPLE for S3"])), "secret"),
        ]
        for raw_payload, expected_err in invalid_cases:
            with self.subTest(expected_err=expected_err):
                out = self.capture("write", "--stdin", "--dry-run", code=1, stdin_text=raw_payload)
                self.assertIn(expected_err, out.stderr + out.stdout)

    def test_dry_run_does_not_create_files_or_dir(self):
        payload_file = self.temp / "payload.json"
        payload_file.write_text(json.dumps(sample_payload()), encoding="utf-8")
        res = self.capture("write", "--payload", payload_file, "--dry-run", "--json")
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "create")
        self.assertTrue(data["dry_run"])
        self.assertIn("+++ b/.byte-stack/playbooks/release-notes.md", data["diff"])
        self.assertFalse(self.local.exists())

    def test_idempotent_repeat_runs_zero_diff_and_mtime_preserved(self):
        raw = json.dumps(sample_payload())
        first = json.loads(self.capture("write", "--stdin", "--json", stdin_text=raw).stdout)
        self.assertEqual(first["status"], "create")
        target = self.local / "playbooks/release-notes.md"
        self.assertTrue(target.is_file())
        umask = os.umask(0)
        os.umask(umask)
        self.assertEqual(target.stat().st_mode & 0o777, 0o666 & ~umask)
        target.chmod(0o640)
        stat_before = (target.stat().st_mode, target.stat().st_mtime_ns, target.read_bytes())

        second = json.loads(self.capture("write", "--stdin", "--json", stdin_text=raw).stdout)
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(second["diff"], "")
        stat_after = (target.stat().st_mode, target.stat().st_mtime_ns, target.read_bytes())
        self.assertEqual(stat_before, stat_after)

        # Clean update preserves custom file permissions (0o640).
        updated = json.dumps(sample_payload(steps=["Check tag", "Generate notes"]))
        self.capture("write", "--stdin", "--update", stdin_text=updated)
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_managed_clean_update_requires_flag(self):
        self.capture("write", "--stdin", stdin_text=json.dumps(sample_payload()))
        target = self.local / "playbooks/release-notes.md"
        v1_bytes = target.read_bytes()

        updated = json.dumps(sample_payload(steps=["Check latest tag", "Generate notes with git log"]))
        conflict = self.capture("write", "--stdin", "--json", code=3, stdin_text=updated)
        conflict_data = json.loads(conflict.stdout)
        self.assertEqual(conflict_data["status"], "conflict")
        self.assertIn("--update", conflict_data["reason"])
        self.assertIn("-1. Find the previous", conflict_data["diff"])
        self.assertEqual(target.read_bytes(), v1_bytes)

        dry_conflict = self.capture("write", "--stdin", "--dry-run", code=3, stdin_text=updated)
        self.assertIn("conflict", dry_conflict.stdout)
        self.assertEqual(target.read_bytes(), v1_bytes)

        applied = json.loads(self.capture("write", "--stdin", "--update", "--json", stdin_text=updated).stdout)
        self.assertEqual(applied["status"], "update")
        self.assertNotEqual(target.read_bytes(), v1_bytes)
        self.capture("validate", target)

    def test_manual_edit_and_hand_authored_protection(self):
        self.capture("write", "--stdin", stdin_text=json.dumps(sample_payload()))
        target = self.local / "playbooks/release-notes.md"
        edited = target.read_text(encoding="utf-8") + "\n<!-- human note -->\n"
        target.write_text(edited, encoding="utf-8")

        updated_payload = json.dumps(sample_payload(title="Release notes v2"))
        for extra_flags in ([], ["--update"]):
            res = self.capture("write", "--stdin", "--json", *extra_flags, code=3, stdin_text=updated_payload)
            data = json.loads(res.stdout)
            self.assertEqual(data["status"], "conflict")
            self.assertIn("managed-modified", data["reason"])
            self.assertIn("<!-- human note -->", data["diff"])
            self.assertEqual(target.read_text(encoding="utf-8"), edited)

        forced = json.loads(self.capture("write", "--stdin", "--force", "--json", stdin_text=updated_payload).stdout)
        self.assertEqual(forced["status"], "force-overwrite")
        self.assertIn("# Release notes v2", target.read_text(encoding="utf-8"))

        hand = self.local / "playbooks/custom.md"
        hand.write_text("# Custom\n\nUse when: Run custom local check.\n\nManual content.\n", encoding="utf-8")
        hand_payload = json.dumps(sample_payload(key="custom.md", title="Custom generated"))
        res = self.capture("write", "--stdin", "--update", "--json", code=3, stdin_text=hand_payload)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "conflict")
        self.assertIn("manual", data["reason"])
        self.assertIn("Manual content.", hand.read_text(encoding="utf-8"))

    def test_strict_validate_command_and_golden_hash(self):
        self.capture("write", "--stdin", stdin_text=json.dumps(sample_payload()))
        target = self.local / "playbooks/release-notes.md"
        content = target.read_text(encoding="utf-8")
        self.assertIn(f"content-sha256: {GOLDEN_SHA256}\n", content)
        self.capture("validate", target)

        valid_without_hash = content.replace(f"content-sha256: {GOLDEN_SHA256}\n", "")
        self.assertEqual(hashlib.sha256(valid_without_hash.encode("utf-8")).hexdigest(), GOLDEN_SHA256)

        bad_cases = [
            (content.replace("Prepare release notes for a tagged version.", "Prepare release notes for /home/alice/repo/"), "machine-local home path"),
            (content.replace('use-when: Prepare release notes for a tagged version.', 'use-when: "Line1\\nLine2 trigger"'), "single line"),
            (content + "tamper\n", "content-sha256 mismatch"),
            (content.replace("managed-by: byte-stack/capture\n", "managed-by: byte-stack/capture\nextra: x\n"), "unknown frontmatter key"),
            (content.replace("schema-version: 1\n", "schema-version: 2\n"), "schema-version"),
            (content.replace("key: release-notes.md\n", "key: other.md\n"), "does not match expected"),
            (content.replace("## Verification\n\n- Confirm every cited commit exists in git log\n", ""), "missing '## Verification'"),
            (content.replace("# Release notes\n", "# Release notes\n\nUse when: Conflicting trigger.\n"), "conflicts with frontmatter"),
        ]
        for mutated, expected_msg in bad_cases:
            with self.subTest(expected_msg=expected_msg):
                target.write_text(mutated, encoding="utf-8")
                res = self.capture("validate", target, code=1)
                self.assertIn(expected_msg, res.stderr)

    def test_symlink_and_outside_git_guards(self):
        outside = self.temp / "outside"
        outside.mkdir()
        raw = json.dumps(sample_payload())

        # Outside Git worktree exits 2 and writes nothing.
        self.capture("write", "--stdin", cwd=outside, code=2, stdin_text=raw)
        self.assertFalse((outside / ".byte-stack").exists())

        # Symlink at .byte-stack exits 2 on dry-run and write.
        self.local.symlink_to(outside, target_is_directory=True)
        for flags in (["--dry-run"], []):
            res = self.capture("write", "--stdin", *flags, code=2, stdin_text=raw)
            self.assertIn("symlink", res.stderr)
        self.local.unlink()

        # Symlink at .byte-stack/playbooks exits 2.
        (self.local / "playbooks").mkdir(parents=True)
        (self.local / "playbooks").rmdir()
        (self.local / "playbooks").symlink_to(outside, target_is_directory=True)
        res = self.capture("write", "--stdin", code=2, stdin_text=raw)
        self.assertIn("symlink", res.stderr)
        (self.local / "playbooks").unlink()

        # Symlink at target file exits 2 and preserves outside file.
        (self.local / "playbooks").mkdir(parents=True)
        victim = outside / "victim.md"
        victim.write_text("do not touch", encoding="utf-8")
        target = self.local / "playbooks/release-notes.md"
        target.symlink_to(victim)
        self.capture("write", "--stdin", "--force", code=2, stdin_text=raw)
        self.capture("validate", target, code=2)
        self.assertEqual(victim.read_text(encoding="utf-8"), "do not touch")
        target.unlink()

        # Directory at target path exits 2.
        target.mkdir()
        res = self.capture("write", "--stdin", code=2, stdin_text=raw)
        self.assertIn("regular file", res.stderr)

    def test_bmode_discovers_and_loads_generated_playbook(self):
        trigger = "Prepare release notes: tagged builds only."
        pb_payload = sample_payload(use_when=trigger)
        wf_payload = {
            "schema_version": 1,
            "kind": "workflows",
            "key": "checks/preflight.md",
            "title": "Preflight checks",
            "steps": ["Run python3 unit tests across the workspace"],
            "verification": ["Confirm exit code 0"],
        }

        self.capture("write", "--stdin", stdin_text=json.dumps(pb_payload))
        self.capture("write", "--stdin", stdin_text=json.dumps(wf_payload))

        listed = self.assets("list-playbooks").stdout
        self.assertIn(f"release-notes.md\t{trigger}", listed)

        resolved_pb = self.assets("resolve", "playbooks", "release-notes.md").stdout.strip()
        expected_pb = (self.local / "playbooks/release-notes.md").resolve()
        self.assertEqual(resolved_pb, f"repo\t{expected_pb}")

        resolved_wf = self.assets("resolve", "workflows", "checks/preflight.md").stdout.strip()
        expected_wf = (self.local / "workflows/checks/preflight.md").resolve()
        self.assertEqual(resolved_wf, f"repo\t{expected_wf}")

    def test_progressive_disclosure_and_skill_budget(self):
        bmode_lines = (SKILLS / "bmode/SKILL.md").read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(bmode_lines), 70)

        skill_md = SKILLS / "capture-playbook/SKILL.md"
        self.assertTrue(skill_md.is_file())
        skill_lines = skill_md.read_text(encoding="utf-8").splitlines()
        desc = next((line.removeprefix("description:").strip() for line in skill_lines if line.startswith("description:")), "")
        self.assertTrue(desc)
        self.assertLessEqual(len(desc), 140)
        self.assertIn("disable-model-invocation: true", skill_lines)

        openai_yaml = SKILLS / "capture-playbook/agents/openai.yaml"
        self.assertTrue(openai_yaml.is_file())
        self.assertIn("allow_implicit_invocation: false", openai_yaml.read_text(encoding="utf-8"))

        self.assertTrue((SKILLS / "bmode/references/capture-playbook.md").is_file())
        self.assertIn("bundled\t", self.assets("resolve", "references", "capture-playbook.md").stdout)
        self.assertTrue((ROOT / "docs/adr/byte-stack-capture.md").is_file())


if __name__ == "__main__":
    unittest.main()
