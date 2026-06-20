"""Tests for the agent factory (canopy create-agent)."""
import json
import subprocess
import sys

import pytest

from orchestrator.agent_factory import (
    AgentSpec,
    AgentFactoryError,
    create_agent,
    normalize_slug,
)


def test_normalize_slug_ok():
    assert normalize_slug("Echo") == "echo"
    assert normalize_slug("sales bot") == "sales-bot"
    assert normalize_slug("partner_outreach") == "partner-outreach"


def test_normalize_slug_rejects_bad():
    with pytest.raises(AgentFactoryError):
        normalize_slug("1bad")          # must start with a letter
    with pytest.raises(AgentFactoryError):
        normalize_slug("x")             # too short
    with pytest.raises(AgentFactoryError):
        normalize_slug("Has Spaces!")   # punctuation


def test_normalize_slug_rejects_builtin_collision():
    # Naming an agent after a Claude Code built-in silently breaks slash dispatch.
    for reserved in ("doctor", "config", "model", "review"):
        with pytest.raises(AgentFactoryError):
            normalize_slug(reserved)


def _spec():
    return AgentSpec(
        slug="echo",
        display_name="Echo",
        mandate="be the marketing agent.",
        mailbox="echo@dimagi-ai.com",
        stakeholders="the Connect team",
    )


def test_create_agent_writes_full_layout(tmp_path):
    written = create_agent(_spec(), tmp_path / "echo")
    names = {p.relative_to(tmp_path / "echo").as_posix() for p in written}
    # The load-bearing primitives must all be present.
    for required in (
        ".claude-plugin/plugin.json",
        "CLAUDE.md",
        "persona.md",
        "config/gating.json",
        ".claude/settings.json",
        "hooks/gating_guard.py",
        "skills/turn/SKILL.md",
        "skills/self-review/SKILL.md",
    ):
        assert required in names, f"missing {required}"


def test_create_agent_substitutes_tokens(tmp_path):
    create_agent(_spec(), tmp_path / "echo")
    claude_md = (tmp_path / "echo" / "CLAUDE.md").read_text()
    assert "Echo" in claude_md
    assert "echo@dimagi-ai.com" in claude_md
    assert "{{" not in claude_md, "an unsubstituted token leaked into output"


def test_generated_json_is_valid(tmp_path):
    create_agent(_spec(), tmp_path / "echo")
    root = tmp_path / "echo"
    for rel in (".claude-plugin/plugin.json", "config/gating.json", ".claude/settings.json"):
        json.loads((root / rel).read_text())  # raises on malformed JSON
    plugin = json.loads((root / ".claude-plugin/plugin.json").read_text())
    assert plugin["name"] == "echo"
    assert plugin["version"] == "0.1.0"


def test_hook_is_executable_and_stdlib_only(tmp_path):
    create_agent(_spec(), tmp_path / "echo")
    hook = tmp_path / "echo" / "hooks" / "gating_guard.py"
    assert hook.stat().st_mode & 0o111, "hook should be executable"
    src = hook.read_text()
    # Hooks run under system python3 which may lack PyYAML — must not import it.
    assert "import yaml" not in src
    assert "import pyyaml" not in src.lower()


def test_create_agent_refuses_nonempty_dir(tmp_path):
    target = tmp_path / "echo"
    target.mkdir()
    (target / "existing.txt").write_text("hi")
    with pytest.raises(AgentFactoryError):
        create_agent(_spec(), target)
    # force=True scaffolds anyway without deleting the pre-existing file.
    create_agent(_spec(), target, force=True)
    assert (target / "existing.txt").exists()
    assert (target / "CLAUDE.md").exists()


def test_gating_hook_blocks_deny_asks_approve_allows_reads(tmp_path):
    """End-to-end: the generated hook enforces deny (exit 2) / approve (ask) / allow."""
    create_agent(_spec(), tmp_path / "echo")
    root = tmp_path / "echo"
    hook = root / "hooks" / "gating_guard.py"

    # Inject a deny rule for raw sends.
    gating = root / "config" / "gating.json"
    cfg = json.loads(gating.read_text())
    cfg["deny"] = [{
        "tool": "Bash",
        "pattern": r"(?:^|[\n;&|(])\s*gog\s+gmail\s+(?:send|reply)\b",
        "message": "BLOCKED: send via the wrapper.",
    }]
    gating.write_text(json.dumps(cfg))

    def run(payload):
        return subprocess.run(
            [sys.executable, str(hook)],
            input=json.dumps(payload), capture_output=True, text=True,
        )

    # deny -> exit 2
    r = run({"tool_name": "Bash", "tool_input": {"command": "gog gmail send --to a@b.c"}})
    assert r.returncode == 2

    # deny pattern only in prose (mid-line) -> NOT blocked
    r = run({"tool_name": "Bash", "tool_input": {"command": "git commit -m 'the gog gmail send rule'"}})
    assert r.returncode == 0

    # approve (Edit) -> ask
    r = run({"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x"}})
    assert r.returncode == 0
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"

    # read (Bash git status) -> allow, no output
    r = run({"tool_name": "Bash", "tool_input": {"command": "git status"}})
    assert r.returncode == 0
    assert r.stdout.strip() == ""
