import json
import os
import subprocess
import sys

import pytest

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
CORE_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "contextboss-core", "src")
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CONTEXTBOSS_DB", str(tmp_path / "hooks.db"))
    monkeypatch.setenv(
        "PYTHONPATH", os.pathsep.join([SRC, CORE_SRC, os.environ.get("PYTHONPATH", "")])
    )
    return tmp_path


def run_hook(hook, event):
    return subprocess.run(
        [sys.executable, "-m", "contextboss_mcp.hooks", hook],
        input=json.dumps(event), capture_output=True, text=True,
        env=dict(os.environ),
    )


class TestClaudeCodeInstall:
    def test_fresh_install(self, env):
        from contextboss_mcp.install import install_claude_code

        install_claude_code()
        settings = json.loads((env / ".claude" / "settings.json").read_text())
        assert settings["mcpServers"]["contextboss"] == {"command": "contextboss-mcp"}
        commands = [
            h["command"]
            for entries in settings["hooks"].values()
            for e in entries
            for h in e["hooks"]
        ]
        assert "contextboss-hook session-start" in commands
        assert commands.count("contextboss-hook snapshot") == 2

    def test_preserves_existing_settings_and_is_idempotent(self, env):
        d = env / ".claude"
        d.mkdir()
        (d / "settings.json").write_text(json.dumps(
            {"model": "opus", "mcpServers": {"other": {"command": "other"}},
             "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "x"}]}]}}
        ))
        from contextboss_mcp.install import install_claude_code

        install_claude_code()
        install_claude_code()  # second run must not duplicate
        settings = json.loads((d / "settings.json").read_text())
        assert settings["model"] == "opus"
        assert "other" in settings["mcpServers"]
        starts = settings["hooks"]["SessionStart"]
        assert len(starts) == 2  # existing + ours, not three

    def test_print_writes_nothing(self, env):
        from contextboss_mcp.install import install_claude_code

        out = install_claude_code(print_only=True)
        assert "contextboss" in out
        assert not (env / ".claude").exists()


class TestCodexInstall:
    def test_install_and_idempotent(self, env, monkeypatch):
        monkeypatch.chdir(env)
        from contextboss_mcp.install import install_codex

        install_codex()
        config = (env / ".codex" / "config.toml").read_text()
        assert "[mcp_servers.contextboss]" in config
        agents = (env / "AGENTS.md").read_text()
        assert "context_add" in agents
        install_codex()
        assert (env / ".codex" / "config.toml").read_text().count(
            "[mcp_servers.contextboss]") == 1
        assert (env / "AGENTS.md").read_text().count("# >>> contextboss >>>") == 1

    def test_appends_to_existing_agents(self, env, monkeypatch):
        monkeypatch.chdir(env)
        (env / "AGENTS.md").write_text("# My project\n\nExisting rules.\n")
        from contextboss_mcp.install import install_codex

        install_codex()
        text = (env / "AGENTS.md").read_text()
        assert text.startswith("# My project")
        assert "# >>> contextboss >>>" in text


class TestHooks:
    def test_session_start_injects_stored_context(self, env):
        from contextboss import ContextManager

        mgr = ContextManager(os.environ["CONTEXTBOSS_DB"])
        mgr.add("deploys freeze on fridays", pinned=True)
        mgr.close()
        res = run_hook("session-start", {"session_id": "s1"})
        assert res.returncode == 0, res.stderr
        out = json.loads(res.stdout)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert "deploys freeze on fridays" in ctx

    def test_session_start_empty_store(self, env):
        res = run_hook("session-start", {})
        assert res.returncode == 0
        out = json.loads(res.stdout)
        assert out["hookSpecificOutput"]["additionalContext"] == ""

    def test_snapshot_records_entry_without_touching_transcript(self, env):
        transcript = env / "transcript.jsonl"
        original = "\n".join(
            json.dumps({"message": {"content": f"discussed item {i}"}})
            for i in range(60)
        )
        transcript.write_text(original)
        res = run_hook("snapshot", {"session_id": "abc", "cwd": "/repo",
                                    "transcript_path": str(transcript)})
        assert res.returncode == 0, res.stderr
        assert transcript.read_text() == original  # read-only

        from contextboss import ContextManager

        mgr = ContextManager(os.environ["CONTEXTBOSS_DB"])
        hits = mgr.search("snapshot", namespace="session-snapshots")
        assert len(hits) == 1
        assert hits[0].metadata["session_id"] == "abc"
        assert "Tail digest" in hits[0].content
        mgr.close()

    def test_snapshot_without_transcript(self, env):
        res = run_hook("snapshot", {"session_id": "no-file"})
        assert res.returncode == 0
