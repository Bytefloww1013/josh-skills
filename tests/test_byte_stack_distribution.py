"""Distribution checks. Host installation tests run when the corresponding CLI is on PATH."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/byte-stack"
BASE = "6bbe7bd206116eb1dc8a116be085ca99169fe0a8"
ARCHIVE = ROOT / "archive/bphs-connect/byte-stack" / BASE[:7] / "source.tar"


class DistributionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.env = dict(os.environ)
        for name in ("HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            path = self.temp / name.lower()
            path.mkdir()
            self.env[name] = str(path)
        self.project = self.temp / "target"
        self.project.mkdir()

    def command(self, *argv, cwd=None):
        result = subprocess.run(argv, cwd=cwd or self.project, env=self.env, capture_output=True,
                                text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return result.stdout.strip()

    def test_archive_tree_and_packaging_blobs(self):
        self.command("tar", "-xf", str(ARCHIVE))
        self.command("git", "init", "-q")
        self.command("git", "-c", "core.filemode=true", "add", "-f", ".")
        tree = self.command("git", "write-tree")
        # Pinned object IDs also verify shallow clones lacking the original commit.
        expected_objects = {
            "plugins/byte-stack": "9eb4fbe94b00bf3f8f82cd223d7c6926bb3ebfb8",
            "README.md": "3359499d4dbf32c78634ed636be0398cae723389",
            ".claude-plugin/marketplace.json": "adcf76e4cb707aaef2c7b8e84aad3efb8540f54f",
        }
        for path, expected in expected_objects.items():
            actual = self.command("git", "rev-parse", f"{tree}:{path}")
            self.assertEqual(actual, expected, path)

    def test_active_package_terms_and_paths(self):
        pattern = (r"bphs-connect|\b(sol|sonnet|opus|haiku|fable|neon|hydrogen|deepseek|hy4)\b"
                   r"|\bgpt[- ](sol|[0-9*])|\b(claude-test|gemini)-[0-9]")
        result = subprocess.run(["rg", "--hidden", "-in", pattern, PLUGIN], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout or result.stderr)
        names = self.command("rg", "--files", "--hidden", str(PLUGIN))
        self.assertNotRegex(names.lower(), pattern)

    @unittest.skipUnless(shutil.which("codex"), "Codex CLI unavailable")
    def test_codex_install(self):
        self.command("codex", "plugin", "marketplace", "add", str(ROOT))
        installed = json.loads(self.command("codex", "plugin", "add", "byte-stack@josh-skills", "--json"))
        listing = json.loads(self.command("codex", "plugin", "list", "--marketplace", "josh-skills", "--json"))
        self.assertTrue(any(p["name"] == "byte-stack" and p["enabled"] for p in listing["installed"]))
        cached = Path(installed["installedPath"])
        self.assertFalse((self.project / ".byte-stack").exists())
        self.assertEqual(json.loads((cached / ".codex-plugin/plugin.json").read_text())["hooks"], [])
        self.assertTrue((cached / "skills/init/scripts/init.py").is_file())
        self.assertTrue((cached / "skills/bmode/scripts/capture_playbook.py").is_file())
        self.assertTrue((cached / "skills/capture-playbook/SKILL.md").is_file())
        self.assertTrue((cached / "skills/extract-assets/SKILL.md").is_file())
        self.assertTrue((cached / "skills/extract-assets/scripts/extract_assets.py").is_file())
        self.assertIn("ByteStackCapturePayload",
                      self.command("python3", cached / "skills/bmode/scripts/capture_playbook.py", "schema"))
        self.assertIn("ByteStackExtractCandidates",
                      self.command("python3", cached / "skills/extract-assets/scripts/extract_assets.py", "schema"))
        self.assertIn("bundled\t", self.command("python3", cached / "skills/bmode/scripts/assets.py",
                                              "resolve", "playbooks", "investigation.md"))

    @unittest.skipUnless(shutil.which("claude"), "Claude Code CLI unavailable")
    def test_claude_install(self):
        self.command("claude", "plugin", "validate", str(PLUGIN))
        self.command("claude", "plugin", "marketplace", "add", str(ROOT))
        self.command("claude", "plugin", "install", "byte-stack@josh-skills")
        details = self.command("claude", "plugin", "details", "byte-stack@josh-skills")
        for name in ("bmode", "init", "capture-playbook", "extract-assets", "review-loop", "byte-agent", "PreCompact"):
            self.assertIn(name, details)
        self.assertFalse((self.project / ".byte-stack").exists())


if __name__ == "__main__":
    unittest.main()
