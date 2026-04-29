"""Tests for orchestrator.skill_runner.

skill_runner shells out to `claude -p`. We never actually invoke Claude in
tests — `subprocess.run` is monkeypatched so we can assert on the cmd it
would have run and simulate its result.
"""
import subprocess

import pytest

from orchestrator.skill_runner import (
    AUTO_SELECT_INSTRUCTION,
    SkillResult,
    build_skill_prompt,
    run_skill,
)


# ---------- build_skill_prompt ----------

def test_prompt_embeds_auto_select_instruction():
    p = build_skill_prompt("/review", "context here")
    assert AUTO_SELECT_INSTRUCTION.strip() in p


def test_prompt_includes_skill_command_and_context():
    p = build_skill_prompt("/qa", "test the MCP server")
    assert "/qa test the MCP server" in p


# ---------- run_skill ----------

class _FakeProc:
    def __init__(self, returncode=0, stdout="ok", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_skill_success_returns_stdout(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeProc(returncode=0, stdout="hello", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_skill("/review", "do stuff")

    assert result.success is True
    assert result.output == "hello"
    assert result.skill == "/review"
    assert result.error is None


def test_run_skill_passes_model_and_budget_to_subprocess(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_skill("/qa", "ctx", model="haiku", max_budget_usd=0.5)

    cmd = captured["cmd"]
    assert "claude" in cmd[0]
    assert "-p" in cmd
    assert "--model" in cmd and "haiku" in cmd
    assert "--max-budget-usd" in cmd and "0.5" in cmd
    assert "--no-session-persistence" in cmd


def test_run_skill_passes_cwd_when_given(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_skill("/x", "ctx", cwd=tmp_path)
    assert captured["kwargs"]["cwd"] == tmp_path


def test_run_skill_omits_cwd_kwarg_when_not_given(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_skill("/x", "ctx")
    assert "cwd" not in captured["kwargs"]


def test_run_skill_nonzero_exit_returns_failure_with_stderr(monkeypatch):
    def fake_run(cmd, **kwargs):
        return _FakeProc(returncode=2, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_skill("/review", "ctx")
    assert result.success is False
    assert result.error == "boom"


def test_run_skill_timeout_returns_failure_with_timeout_message(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_skill("/review", "ctx", timeout=42)
    assert result.success is False
    assert result.output == ""
    assert "Timeout after 42s" in (result.error or "")


def test_run_skill_passes_timeout_to_subprocess(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_skill("/x", "ctx", timeout=99)
    assert captured["kwargs"]["timeout"] == 99


def test_run_skill_clears_error_on_success(monkeypatch):
    """Even if stderr has noise, success means error=None."""
    def fake_run(cmd, **kwargs):
        return _FakeProc(returncode=0, stdout="ok", stderr="harmless warning")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_skill("/x", "ctx")
    assert result.success is True
    assert result.error is None
