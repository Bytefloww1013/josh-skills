#!/usr/bin/env python3
"""Antigravity plugin install smoke test (standard library only).

Installs both plugins (`arch-skills` and `byte-stack`) with `agy plugin install`
into a temporary isolated HOME/config, validates the installed trees with
`agy plugin validate --strict`, checks agent metadata and hook registration, and
invokes the installed `arch-skills` PR reminder hook for both Antigravity and
Claude Code payloads on docs-only, code-change, rename, and unknown-base fixtures,
and for Antigravity's PreInvocation delivery of a kept reminder.

Usage:
  python3 tests/test_antigravity_plugin_install.py [--help]

Exit codes:
  0  All smoke checks passed.
  1  One or more smoke checks failed.
  2  Prerequisite missing (`agy` CLI not found on PATH).
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_PREREQ_MISSING = 2

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"


def parse_frontmatter(markdown_text):
    """Minimal stdlib YAML frontmatter parser for simple scalar key: value pairs."""
    lines = markdown_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, markdown_text
    meta = {}
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
        line = lines[idx]
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip()
    body = "\n".join(lines[end_idx + 1 :]) if end_idx is not None else ""
    return meta, body


def run_cmd(args, *, env=None, cwd=None, stdin_text=None, timeout=30):
    return subprocess.run(
        args,
        input=stdin_text,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def git(repo, env, *args):
    out = run_cmd(["git", "-C", str(repo), *args], env=env)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def make_branch(repo, env, files):
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, env, "init", "-b", "main")
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    git(repo, env, "add", ".")
    git(repo, env, "commit", "-m", "init")
    git(repo, env, "checkout", "-b", "feat/smoke-fixture")
    for name in files:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
    git(repo, env, "add", ".")
    git(repo, env, "commit", "-m", "change")


def main():
    if sys.argv[1:2] in (["-h"], ["--help"]):
        print(__doc__.strip())
        return EXIT_OK

    agy = shutil.which("agy")
    if not agy:
        print(
            "PREREQUISITE MISSING: `agy` CLI was not found on PATH. "
            "Install Antigravity CLI or add it to PATH to run this smoke test.",
            file=sys.stderr,
        )
        print("RESULT: PREREQUISITE MISSING (exit 2)")
        return EXIT_PREREQ_MISSING

    failed = 0

    def check(label, ok, detail=""):
        nonlocal failed
        if not ok:
            failed += 1
        suffix = "" if ok else f" ({detail})"
        print(f"{'PASS' if ok else 'FAIL'}: {label}{suffix}")

    with tempfile.TemporaryDirectory(prefix="agy-plugin-smoke-") as tmp_str:
        tmp = Path(tmp_str)
        env = {
            **os.environ,
            "HOME": str(tmp / "home"),
            "GEMINI_HOME": str(tmp / "gemini"),
            "XDG_CONFIG_HOME": str(tmp / "xdg_config"),
            "XDG_DATA_HOME": str(tmp / "xdg_data"),
            "XDG_CACHE_HOME": str(tmp / "xdg_cache"),
            "GIT_AUTHOR_NAME": "Smoke Test",
            "GIT_AUTHOR_EMAIL": "smoke@example.invalid",
            "GIT_COMMITTER_NAME": "Smoke Test",
            "GIT_COMMITTER_EMAIL": "smoke@example.invalid",
        }
        for key in ("HOME", "GEMINI_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            Path(env[key]).mkdir(parents=True, exist_ok=True)

        # Safety pre-check: confirm isolation before any mutating agy command.
        pre = run_cmd([agy, "plugin", "list", "--json"], env=env)
        try:
            pre_plugins = json.loads(pre.stdout)
        except ValueError:
            pre_plugins = None
        if pre.returncode != 0 or pre_plugins != []:
            print(
                f"FAIL: isolation pre-check failed (rc={pre.returncode}, stdout={pre.stdout!r}, stderr={pre.stderr!r})",
                file=sys.stderr,
            )
            return EXIT_FAIL
        check("isolation: isolated HOME starts with empty plugin list", True)

        # 1. Install both plugins from this checkout.
        arch_src = PLUGINS_DIR / "arch-skills"
        byte_src = PLUGINS_DIR / "byte-stack"
        arch_inst = run_cmd([agy, "plugin", "install", str(arch_src)], env=env)
        check(
            "install arch-skills exits 0",
            arch_inst.returncode == 0,
            arch_inst.stderr.strip() or arch_inst.stdout.strip(),
        )
        byte_inst = run_cmd([agy, "plugin", "install", str(byte_src)], env=env)
        byte_inst_out = byte_inst.stdout + byte_inst.stderr
        check(
            "install byte-stack exits 0 without skipped-hook warnings",
            byte_inst.returncode == 0
            and "PreCompact" not in byte_inst_out
            and "UserPromptSubmit" not in byte_inst_out,
            byte_inst_out.strip(),
        )

        # 2. Verify agy plugin list --json reports versions, components, and paths.
        listed = run_cmd([agy, "plugin", "list", "--json"], env=env)
        plugins_by_name = {}
        if listed.returncode == 0:
            try:
                plugins_by_name = {p["name"]: p for p in json.loads(listed.stdout)}
            except (ValueError, KeyError, TypeError):
                plugins_by_name = {}

        arch_src_ver = json.loads((arch_src / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        arch_agy_ver = json.loads((arch_src / ".antigravity-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        check(
            "arch-skills: the Claude Code and Antigravity manifests have the same version",
            arch_src_ver == arch_agy_ver,
            f"claude={arch_src_ver!r}, antigravity={arch_agy_ver!r}",
        )
        byte_claude = json.loads((byte_src / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        byte_agy_ver = json.loads((byte_src / ".antigravity-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        # Claude Code takes a plugin with no `version` from the commit, so each push is an update. A `version` there
        # would pin the plugin until someone changed the number.
        check(
            "byte-stack: the Antigravity manifest has the version, the Claude Code manifest has none",
            bool(byte_agy_ver) and "version" not in byte_claude,
            f"claude={byte_claude.get('version')!r}, antigravity={byte_agy_ver!r}",
        )

        arch_entry = plugins_by_name.get("arch-skills") or {}
        byte_entry = plugins_by_name.get("byte-stack") or {}
        check(
            "arch-skills listed as enabled with source version, 6 skills, and 1 hook group",
            arch_entry.get("enabled") is True
            and arch_entry.get("version") == arch_src_ver
            and len(arch_entry.get("skills") or []) == 6
            and arch_entry.get("hooks") == ["arch-skills"],
            arch_entry,
        )
        check(
            "byte-stack listed as enabled with source version, byte-agent, and no hooks",
            byte_entry.get("enabled") is True
            and byte_entry.get("version") == byte_agy_ver
            and byte_entry.get("agents") == ["byte-agent"]
            and "bmode" in (byte_entry.get("skills") or [])
            and "byte-handoff" in (byte_entry.get("skills") or [])
            and not byte_entry.get("hooks"),
            byte_entry,
        )

        arch_dir = Path(arch_entry["path"]) if arch_entry.get("path") else Path(env["HOME"]) / ".gemini" / "config" / "plugins" / "arch-skills"
        byte_dir = Path(byte_entry["path"]) if byte_entry.get("path") else Path(env["HOME"]) / ".gemini" / "config" / "plugins" / "byte-stack"

        # 3. Validate both installed directories with `agy plugin validate --strict --json`.
        # Both plugins keep their Claude Code hooks in `hooks/hooks.json`. Antigravity reads plugin hooks only from a
        # `hooks.json` at the plugin root, so it loads none of them and warns about that file. That warning is the
        # wanted result: byte-stack's handoff guard is Claude Code only, and arch-skills ships its Antigravity hooks
        # in its own root `hooks.json`. Any other warning or error fails.
        expected_warnings = {"arch-skills": ["hooks/hooks.json"], "byte-stack": ["hooks/hooks.json"]}
        for name, installed_dir in (("arch-skills", arch_dir), ("byte-stack", byte_dir)):
            val = run_cmd([agy, "plugin", "validate", str(installed_dir), "--strict", "--json"], env=env)
            try:
                findings = json.loads(val.stdout[: val.stdout.rindex("}") + 1]).get("findings") or []
                errors = [f for f in findings if f.get("severity") == "error"]
                warned = sorted(f.get("file") for f in findings if f.get("severity") == "warning")
                val_ok = not errors and warned == expected_warnings[name] and (val.returncode == 0) == (not warned)
                detail = str(errors or [f for f in findings if f.get("severity") == "warning"])
            except ValueError as exc:
                val_ok = False
                detail = f"non-JSON validate output: {exc}: {val.stderr.strip() or val.stdout.strip()}"
            label = "passes" if not expected_warnings[name] else "warns only that hooks/hooks.json is never loaded"
            check(f"agy plugin validate --strict {label} for installed {name}", val_ok, detail)

        # 4. Inspect registered hook events on disk.
        arch_hooks_path = arch_dir / "hooks.json"
        arch_hooks = json.loads(arch_hooks_path.read_text(encoding="utf-8")) if arch_hooks_path.is_file() else {}
        arch_group = arch_hooks.get("arch-skills") or {}
        pre_tool = arch_group.get("PreToolUse") or []
        pre_invocation = arch_group.get("PreInvocation") or []
        arch_hook_script = arch_dir / "hooks" / "pre_pr_reminder.py"
        check(
            "arch-skills registers only PreToolUse(run_command) and PreInvocation, both running ./hooks/pre_pr_reminder.py",
            set(arch_group.keys()) == {"PreToolUse", "PreInvocation"}
            and len(pre_tool) == 1
            and pre_tool[0].get("matcher") == "run_command"
            and [shlex.split(h.get("command", "")) for h in pre_tool[0].get("hooks") or []]
            == [["python3", "./hooks/pre_pr_reminder.py"]]
            and [shlex.split(h.get("command", "")) for h in pre_invocation]
            == [["python3", "./hooks/pre_pr_reminder.py"]]
            and arch_hook_script.is_file(),
            arch_hooks,
        )

        byte_hooks_path = byte_dir / "hooks.json"
        byte_hooks = json.loads(byte_hooks_path.read_text(encoding="utf-8")) if byte_hooks_path.is_file() else {}
        check(
            "byte-stack registers no Antigravity hooks",
            not byte_hooks_path.exists() or byte_hooks == {},
            byte_hooks,
        )

        # 5. Inspect installed byte-agent metadata and `agy agents` visibility.
        agent_path = byte_dir / "agents" / "byte-agent.md"
        meta, body = parse_frontmatter(agent_path.read_text(encoding="utf-8")) if agent_path.is_file() else ({}, "")
        check(
            "byte-agent frontmatter sets subagent: true, mainAgent: false, and omits harness-specific tools",
            meta.get("name") == "byte-agent"
            and meta.get("subagent") == "true"
            and meta.get("mainAgent") == "false"
            and "tools" not in meta,
            meta,
        )
        check(
            "byte-agent body searches Gemini and Claude plugin paths for skills/bmode/SKILL.md",
            all(
                needle in body
                for needle in (
                    "$GEMINI_HOME/config/plugins/",
                    "~/.gemini/config/plugins/",
                    ".agents/plugins/",
                    "~/.claude/plugins/",
                    "skills/bmode/SKILL.md",
                )
            ),
            body,
        )
        agents_out = run_cmd([agy, "agents"], env=env)
        check(
            "agy agents hides byte-agent from primary agents (mainAgent: false)",
            agents_out.returncode == 0 and "byte-agent" not in agents_out.stdout.splitlines(),
            agents_out.stdout.strip() or agents_out.stderr.strip(),
        )

        # 6. Run the INSTALLED reminder hook (with cwd=installed arch-skills dir) for both payload shapes.
        docs_repo = tmp / "fixtures" / "docs-only"
        make_branch(docs_repo, env, ["GLOSSARY.md", "docs/guide.mdx", "notes.txt"])

        code_repo = tmp / "fixtures" / "code-change"
        make_branch(code_repo, env, ["GLOSSARY.md", "src/app.py"])

        rename_repo = tmp / "fixtures" / "code-renamed-to-doc"
        make_branch(rename_repo, env, ["app.py"])
        git(rename_repo, env, "branch", "before-rename")
        git(rename_repo, env, "mv", "app.py", "app.md")
        git(rename_repo, env, "commit", "-m", "rename")

        non_git = tmp / "fixtures" / "not-a-repo"
        non_git.mkdir(parents=True)

        hook_env = {**env, "PLUGIN_DATA": str(tmp / "plugin_data" / "arch-skills")}

        def invoke_installed(payload):
            proc = run_cmd(
                [sys.executable, str(arch_hook_script)],
                env=hook_env,
                cwd=arch_dir,
                stdin_text=json.dumps(payload),
            )
            if proc.returncode != 0:
                raise RuntimeError(f"hook exited {proc.returncode}: {proc.stderr.strip()}")
            return proc.stdout.strip()

        def agy_payload(command, cwd, arg_key="CommandLine"):
            return {
                "hookEventName": "PreToolUse",
                "cwd": str(cwd),
                "toolCall": {
                    "id": "toolu_smoke",
                    "name": "run_command",
                    "args": {arg_key: command},
                },
            }

        def claude_payload(command, cwd):
            return {"tool_input": {"command": command}, "cwd": str(cwd)}

        # Antigravity payload checks
        raw = invoke_installed(agy_payload("git status", code_repo))
        check("installed hook (Antigravity, non-PR cmd): allow without reason", json.loads(raw) == {"decision": "allow"}, raw)

        raw = invoke_installed(agy_payload("gh pr create --base main --title t", docs_repo))
        check("installed hook (Antigravity, docs-only): allow without reason", json.loads(raw) == {"decision": "allow"}, raw)

        raw = invoke_installed(agy_payload("gh pr create --base main --title t", code_repo))
        parsed = json.loads(raw)
        check(
            "installed hook (Antigravity, code branch): allow with pr-erosion-check reason",
            parsed.get("decision") == "allow" and "pr-erosion-check" in parsed.get("reason", ""),
            raw,
        )

        raw = invoke_installed(agy_payload("gh pr create --base main --title t", code_repo, arg_key="command"))
        parsed = json.loads(raw)
        check(
            "installed hook (Antigravity, lowercase args.command): allow with pr-erosion-check reason",
            parsed.get("decision") == "allow" and "pr-erosion-check" in parsed.get("reason", ""),
            raw,
        )

        raw = invoke_installed(agy_payload("gh pr create --base before-rename", rename_repo))
        parsed = json.loads(raw)
        check(
            "installed hook (Antigravity, code-to-doc rename): allow with pr-erosion-check reason",
            parsed.get("decision") == "allow" and "pr-erosion-check" in parsed.get("reason", ""),
            raw,
        )

        raw = invoke_installed(agy_payload("gh pr create --title t", non_git))
        parsed = json.loads(raw)
        check(
            "installed hook (Antigravity, unknown base/non-git): allow with pr-erosion-check reason",
            parsed.get("decision") == "allow" and "pr-erosion-check" in parsed.get("reason", ""),
            raw,
        )

        # Antigravity drops `reason` on an allowed call: with a conversationId the reminder is kept and the
        # PreInvocation hook sends it once before the next model call.
        kept_call = {**agy_payload("gh pr create --base main --title t", code_repo), "conversationId": "conv-smoke"}
        raw = invoke_installed(kept_call)
        check("installed hook (Antigravity, code branch, conversation): plain allow", json.loads(raw) == {"decision": "allow"}, raw)
        model_call = {"hookEventName": "PreInvocation", "conversationId": "conv-smoke", "invocationNum": 2}
        raw = invoke_installed(model_call)
        steps = (json.loads(raw).get("injectSteps") or [{}]) if raw else [{}]
        check(
            "installed hook (Antigravity, PreInvocation): sends the kept reminder as a system message",
            "pr-erosion-check" in ((steps[0].get("systemMessage") or {}).get("systemMessage") or ""),
            raw,
        )
        raw = invoke_installed(model_call)
        check("installed hook (Antigravity, PreInvocation again): empty answer", json.loads(raw) == {}, raw)

        # Claude Code payload checks
        raw = invoke_installed(claude_payload("git status", code_repo))
        check("installed hook (Claude, non-PR cmd): empty stdout", raw == "", raw)

        raw = invoke_installed(claude_payload("gh pr create --base main --title t", docs_repo))
        check("installed hook (Claude, docs-only): empty stdout", raw == "", raw)

        raw = invoke_installed(claude_payload("gh pr create --base main --title t", code_repo))
        parsed = json.loads(raw)
        hook_out = parsed.get("hookSpecificOutput") or {}
        check(
            "installed hook (Claude, code branch): PreToolUse additionalContext reminder",
            hook_out.get("hookEventName") == "PreToolUse" and "pr-erosion-check" in hook_out.get("additionalContext", ""),
            raw,
        )

        raw = invoke_installed(claude_payload("gh pr create --base before-rename", rename_repo))
        parsed = json.loads(raw)
        hook_out = parsed.get("hookSpecificOutput") or {}
        check(
            "installed hook (Claude, code-to-doc rename): PreToolUse additionalContext reminder",
            hook_out.get("hookEventName") == "PreToolUse" and "pr-erosion-check" in hook_out.get("additionalContext", ""),
            raw,
        )

        raw = invoke_installed(claude_payload("gh pr create --title t", non_git))
        parsed = json.loads(raw)
        hook_out = parsed.get("hookSpecificOutput") or {}
        check(
            "installed hook (Claude, unknown base/non-git): PreToolUse additionalContext reminder",
            hook_out.get("hookEventName") == "PreToolUse" and "pr-erosion-check" in hook_out.get("additionalContext", ""),
            raw,
        )

    print(f"RESULT: {'PASS' if not failed else f'FAIL ({failed} failed)'}")
    return EXIT_FAIL if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
