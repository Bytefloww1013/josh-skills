"""Opt-in smoke test using four signed-in Claude Code turns in a disposable checkout."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*command, cwd, env=None, timeout=120):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout[-1000:])
    return result.stdout


def turn(plugin, cwd, prompt, expected_output):
    output = run(
        "claude", "--plugin-dir", plugin, "--setting-sources", "project,local",
        "--no-session-persistence", "--strict-mcp-config", "--settings", '{"disableAllHooks":true}',
        "--tools", "Bash,Read,Skill", "--allowedTools", "Bash,Read,Skill", "--verbose",
        "--output-format", "stream-json", "-p", prompt, cwd=cwd,
    )
    events = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    for event in events:
        if event.get("type") != "user":
            continue
        for block in event.get("message", {}).get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                if expected_output in str(block.get("content", "")) and not block.get("is_error"):
                    return next(e["result"] for e in reversed(events) if e["type"] == "result")
    raise AssertionError(f"no successful tool output containing {expected_output!r}")


def snapshot(folder):
    return {p.relative_to(folder): (p.stat().st_mode, p.stat().st_mtime_ns,
                                    p.read_bytes() if p.is_file() else None)
            for p in folder.rglob("*")}


def main():
    with tempfile.TemporaryDirectory() as temp:
        scratch = Path(temp)
        repo = scratch / "fixture"
        run("git", "init", "-q", repo, cwd=scratch)
        nested = repo / "nested"
        nested.mkdir()
        proof = repo / "proof.txt"
        proof.write_text("Status: sapphire.\n")
        config = scratch / "install-profile"
        config.mkdir()
        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(config)}
        run("claude", "plugin", "marketplace", "add", ROOT, cwd=repo, env=env)
        run("claude", "plugin", "install", "byte-stack@josh-skills", cwd=repo, env=env)
        [entry] = config.glob("plugins/cache/**/skills/bmode/SKILL.md")
        plugin = entry.parents[2]
        local = repo / ".byte-stack"
        assert not local.exists()
        prompt = "/byte-stack:bmode investigation.md What status is in proof.txt? Report the resolver output."
        bundled = entry.parent / "playbooks/investigation.md"
        before = run("git", "status", "--porcelain", cwd=repo)
        reply = turn(plugin, nested, prompt, f"bundled\t{bundled}")
        assert "sapphire" in reply.lower() and before == run("git", "status", "--porcelain", cwd=repo)
        assert not local.exists()
        print("PASS bundled bmode fallback", flush=True)
        override = local / "playbooks/investigation.md"
        override.parent.mkdir(parents=True)
        override.write_text("Read proof.txt at the worktree root. Include OBSERVED-BRAMBLE with the status.")
        original = snapshot(local)[override.relative_to(local)]
        turn(plugin, nested, "/byte-stack:init", f"Created {local}")
        initialized = snapshot(local)
        assert {p.name for p in local.iterdir()} == {"playbooks", "workflows", "scripts", "references"}
        assert initialized[override.relative_to(local)] == original
        turn(plugin, nested, "/byte-stack:init", f"Already initialized: {local}")
        assert initialized == snapshot(local)
        print("PASS installed init twice; user file, modes and times preserved", flush=True)
        reply = turn(plugin, nested, prompt, f"repo\t{override}")
        assert "OBSERVED-BRAMBLE" in reply and "sapphire" in reply.lower()
        assert initialized == snapshot(local)
        print("PASS local bmode override")


if __name__ == "__main__":
    main()
