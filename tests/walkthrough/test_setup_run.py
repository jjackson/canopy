"""Unit tests for ``record_video.run_setup`` (the data-setup execution contract).

The subprocess is mocked — these pin the orchestration semantics, not shell
behavior:

  - ``rerun: per_render`` (default) runs the command on EVERY invocation —
    required for state-mutating demos, where recording itself changes the
    world (PAR's manager flow creates a real audit + task, so a re-render
    without a reseed films "View Audit" instead of "Create Audit").
  - ``rerun: once`` skips the command when the outputs file already exists.
  - ``--skip-setup`` skips the command unconditionally but still loads outputs.
  - Nonzero exit and timeout abort loudly (``SetupError``) before any browser.
  - Provenance (command, cwd, exit code, duration, resolved variables) is
    returned for the RunReport / ``setup-vars.json`` evidence chain.
  - ``resolve_setup_cwd``: the git toplevel containing the SPEC file (not the
    recorder's cwd), falling back to the spec's directory outside a git repo.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough import record_video  # noqa: E402
from scripts.walkthrough.record_video import (  # noqa: E402
    SetupError,
    load_setup_outputs,
    resolve_setup_cwd,
    run_setup,
)


class _FakeCompleted:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    """A spec file + outputs file in tmp_path, with cwd resolution pinned there."""
    spec_path = tmp_path / "docs" / "walkthroughs" / "demo.yaml"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text("name: demo\n")
    outputs = tmp_path / "scripts" / "walkthroughs" / "demo" / "outputs.json"
    outputs.parent.mkdir(parents=True)
    monkeypatch.setattr(record_video, "resolve_setup_cwd", lambda p: tmp_path)
    return spec_path, outputs


def _setup_dict(**overrides) -> dict:
    base = {
        "command": "python scripts/walkthroughs/demo/regenerate.py",
        "outputs": "scripts/walkthroughs/demo/outputs.json",
    }
    base.update(overrides)
    return base


def test_per_render_runs_command_every_time(setup_env, monkeypatch):
    spec_path, outputs = setup_env
    outputs.write_text(json.dumps({"run_id": 3721}))  # exists — per_render runs anyway
    calls: list = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeCompleted(0)

    monkeypatch.setattr(record_video.subprocess, "run", fake_run)
    prov = run_setup(_setup_dict(), spec_path)
    assert len(calls) == 1
    assert calls[0][1]["shell"] is True
    assert calls[0][1]["cwd"] == str(spec_path.parents[2])  # the resolved repo root
    assert prov["skipped"] is False
    assert prov["exit_code"] == 0
    assert prov["duration_seconds"] is not None
    assert prov["variables"] == {"run_id": 3721}


def test_rerun_once_skips_when_outputs_exists(setup_env, monkeypatch):
    spec_path, outputs = setup_env
    outputs.write_text(json.dumps({"run_id": 3721}))

    def boom(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("command must not run when rerun=once and outputs exists")

    monkeypatch.setattr(record_video.subprocess, "run", boom)
    prov = run_setup(_setup_dict(rerun="once"), spec_path)
    assert prov["skipped"] is True
    assert "rerun=once" in prov["skip_reason"]
    assert prov["variables"] == {"run_id": 3721}


def test_rerun_once_runs_when_outputs_missing(setup_env, monkeypatch):
    spec_path, outputs = setup_env
    calls: list = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        outputs.write_text(json.dumps({"run_id": 9}))
        return _FakeCompleted(0)

    monkeypatch.setattr(record_video.subprocess, "run", fake_run)
    prov = run_setup(_setup_dict(rerun="once"), spec_path)
    assert len(calls) == 1
    assert prov["variables"] == {"run_id": 9}


def test_skip_setup_skips_command_but_loads_outputs(setup_env, monkeypatch):
    spec_path, outputs = setup_env
    outputs.write_text(json.dumps({"run_id": 3721, "task_id": "T-1"}))

    def boom(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("command must not run under --skip-setup")

    monkeypatch.setattr(record_video.subprocess, "run", boom)
    prov = run_setup(_setup_dict(), spec_path, skip_setup=True)
    assert prov["skipped"] is True
    assert prov["skip_reason"] == "--skip-setup"
    assert prov["variables"] == {"run_id": 3721, "task_id": "T-1"}


def test_nonzero_exit_aborts_loudly(setup_env, monkeypatch):
    spec_path, _ = setup_env
    monkeypatch.setattr(record_video.subprocess, "run", lambda *a, **k: _FakeCompleted(3))
    with pytest.raises(SetupError, match="exit 3"):
        run_setup(_setup_dict(), spec_path)


def test_timeout_aborts_loudly(setup_env, monkeypatch):
    spec_path, _ = setup_env

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(record_video.subprocess, "run", fake_run)
    with pytest.raises(SetupError, match="timed out after 5s"):
        run_setup(_setup_dict(timeout_seconds=5), spec_path)


def test_declared_outputs_missing_after_run_is_error(setup_env, monkeypatch):
    spec_path, _ = setup_env  # outputs file never written
    monkeypatch.setattr(record_video.subprocess, "run", lambda *a, **k: _FakeCompleted(0))
    with pytest.raises(SetupError, match="outputs file not found"):
        run_setup(_setup_dict(), spec_path)


def test_no_outputs_declared_yields_empty_variables(setup_env, monkeypatch):
    spec_path, _ = setup_env
    monkeypatch.setattr(record_video.subprocess, "run", lambda *a, **k: _FakeCompleted(0))
    prov = run_setup(_setup_dict(outputs=None), spec_path)
    assert prov["variables"] == {}


def test_invalid_rerun_value_is_error(setup_env):
    spec_path, _ = setup_env
    with pytest.raises(SetupError, match="rerun must be per_render"):
        run_setup(_setup_dict(rerun="sometimes"), spec_path)


# ---------------------------------------------------------------------------
# load_setup_outputs — the flat string/number contract
# ---------------------------------------------------------------------------


def test_load_outputs_rejects_non_object(tmp_path):
    p = tmp_path / "outputs.json"
    p.write_text(json.dumps([1, 2, 3]))
    with pytest.raises(SetupError, match="flat JSON object"):
        load_setup_outputs(p)


def test_load_outputs_rejects_nested_values(tmp_path):
    p = tmp_path / "outputs.json"
    p.write_text(json.dumps({"run": {"id": 1}}))
    with pytest.raises(SetupError, match="strings or numbers"):
        load_setup_outputs(p)


def test_load_outputs_accepts_strings_and_numbers(tmp_path):
    p = tmp_path / "outputs.json"
    p.write_text(json.dumps({"run_id": 3721, "rate": 0.5, "slug": "par-q2"}))
    assert load_setup_outputs(p) == {"run_id": 3721, "rate": 0.5, "slug": "par-q2"}


# ---------------------------------------------------------------------------
# resolve_setup_cwd — git toplevel of the SPEC, not the recorder's cwd
# ---------------------------------------------------------------------------


def test_resolve_setup_cwd_finds_git_toplevel(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    spec = tmp_path / "docs" / "walkthroughs" / "demo.yaml"
    spec.parent.mkdir(parents=True)
    spec.write_text("name: demo\n")
    assert resolve_setup_cwd(spec).resolve() == tmp_path.resolve()


def test_resolve_setup_cwd_falls_back_to_spec_dir(tmp_path, monkeypatch):
    spec = tmp_path / "demo.yaml"
    spec.write_text("name: demo\n")
    # Simulate "not in a git repo" regardless of where tmp_path actually lives.
    monkeypatch.setattr(
        record_video.subprocess, "run",
        lambda *a, **k: _FakeCompleted(128),
    )
    assert resolve_setup_cwd(spec) == tmp_path
