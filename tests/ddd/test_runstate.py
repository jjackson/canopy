"""Tests for DDD run-state lifecycle (SP0.4)."""
import re
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_ddd_dir(monkeypatch, tmp_path: Path) -> Path:
    """Point the runstate module to a tmp dir so tests don't pollute the repo."""
    ddd_dir = tmp_path / ".canopy" / "ddd"
    ddd_dir.mkdir(parents=True)
    # Monkeypatch the resolver used by runstate. _resolve_ddd_dir now accepts an
    # optional repo_root arg, so the stub must swallow any args/kwargs.
    import scripts.ddd.runstate as rs
    monkeypatch.setattr(rs, "_resolve_ddd_dir", lambda *a, **k: ddd_dir)
    return ddd_dir


# ---------------------------------------------------------------------------
# SP0.4 — new_run creates run_state.yaml with phase=="phase0"
# ---------------------------------------------------------------------------

def test_new_run_creates_run_state(tmp_path, monkeypatch):
    ddd_dir = _patch_ddd_dir(monkeypatch, tmp_path)

    from scripts.ddd.runstate import new_run

    run_id = new_run("sampling-engine")
    run_dir = ddd_dir / "runs" / run_id
    assert run_dir.is_dir()

    state_file = run_dir / "run_state.yaml"
    assert state_file.exists()

    raw = yaml.safe_load(state_file.read_text())
    assert raw["phase"] == "phase0"
    assert raw["narrative_slug"] == "sampling-engine"
    assert raw["schema_version"] == 1


def test_new_run_id_format(tmp_path, monkeypatch):
    _patch_ddd_dir(monkeypatch, tmp_path)

    from scripts.ddd.runstate import new_run

    run_id = new_run("my-narrative_slug")
    # Expected pattern: <narrative_slug>-<YYYY-MM-DD>-NNN
    assert re.match(r"^my-narrative_slug-\d{4}-\d{2}-\d{2}-\d{3}$", run_id), (
        f"run_id '{run_id}' does not match expected pattern"
    )


def test_new_run_sequential_numbering(tmp_path, monkeypatch):
    _patch_ddd_dir(monkeypatch, tmp_path)

    from scripts.ddd.runstate import new_run

    id1 = new_run("feat")
    id2 = new_run("feat")
    # Both should exist and be different
    assert id1 != id2
    # Second should be -002 if first was -001
    assert id2.endswith("-002") if id1.endswith("-001") else True


# ---------------------------------------------------------------------------
# SP0.4 — save / load round-trip
# ---------------------------------------------------------------------------

def test_save_load_round_trips(tmp_path, monkeypatch):
    _patch_ddd_dir(monkeypatch, tmp_path)

    from scripts.ddd.runstate import new_run, load, save
    from scripts.ddd.schemas.models import RunState

    run_id = new_run("round-trip-narrative_slug")
    state = load(run_id)

    assert isinstance(state, RunState)
    assert state.phase == "phase0"

    # Mutate and save
    state.phase = "spec"
    state.iteration = 1
    state.last_actor = "alice"
    save(state)

    # Reload and verify
    state2 = load(run_id)
    assert state2.phase == "spec"
    assert state2.iteration == 1
    assert state2.last_actor == "alice"


# ---------------------------------------------------------------------------
# SP0.4 — append_learning writes to learnings.md
# ---------------------------------------------------------------------------

def test_append_learning_creates_and_appends(tmp_path, monkeypatch):
    ddd_dir = _patch_ddd_dir(monkeypatch, tmp_path)

    from scripts.ddd.runstate import append_learning

    learnings_file = ddd_dir / "learnings.md"
    assert not learnings_file.exists()

    append_learning("First learning: always validate early.")
    assert learnings_file.exists()
    content = learnings_file.read_text()
    assert "First learning" in content

    append_learning("Second learning: test everything.")
    content2 = learnings_file.read_text()
    assert "First learning" in content2
    assert "Second learning" in content2


# ---------------------------------------------------------------------------
# Fix 2: _resolve_ddd_dir falls back to home path when git is absent (FileNotFoundError)
# ---------------------------------------------------------------------------

def test_resolve_ddd_dir_fallback_when_git_absent(monkeypatch, tmp_path):
    """When git is not on PATH (FileNotFoundError), fall back to $HOME/.canopy/ddd/<cwd-name>/."""
    import subprocess
    import scripts.ddd.runstate as rs

    # DDD_DIR env now takes precedence over the git-cwd logic; clear it so this
    # test exercises the git-absent fallback path it was written for.
    monkeypatch.delenv("DDD_DIR", raising=False)

    # Make subprocess.check_output raise FileNotFoundError (git not on PATH)
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError("git not found")))

    # Run the resolver (we don't monkeypatch _resolve_ddd_dir here — we test the real one)
    result = rs._resolve_ddd_dir()

    import os
    cwd_name = Path(os.getcwd()).name
    expected = Path.home() / ".canopy" / "ddd" / cwd_name
    assert result == expected, f"Expected {expected}, got {result}"
    # The dir should have been created
    assert result.is_dir()


# ---------------------------------------------------------------------------
# Task 12: _resolve_ddd_dir overrides (repo_root arg / DDD_DIR env) +
#          per-call ddd_dir on load/save/new_run
# ---------------------------------------------------------------------------

def test_resolve_ddd_dir_repo_root_arg(tmp_path, monkeypatch):
    """An explicit repo_root arg yields <repo_root>/.canopy/ddd and creates it."""
    import scripts.ddd.runstate as rs

    result = rs._resolve_ddd_dir(repo_root=tmp_path)
    assert result == tmp_path / ".canopy" / "ddd"
    assert result.is_dir()


def test_resolve_ddd_dir_honors_ddd_dir_env(tmp_path, monkeypatch):
    """DDD_DIR env is honored by _resolve_ddd_dir() with no args (and created)."""
    import scripts.ddd.runstate as rs

    target = tmp_path / "from-env"
    monkeypatch.setenv("DDD_DIR", str(target))
    result = rs._resolve_ddd_dir()
    assert result == target
    assert result.is_dir()


def test_resolve_ddd_dir_repo_root_beats_env(tmp_path, monkeypatch):
    """Explicit repo_root arg wins over DDD_DIR env."""
    import scripts.ddd.runstate as rs

    monkeypatch.setenv("DDD_DIR", str(tmp_path / "env-dir"))
    repo_root = tmp_path / "repo"
    result = rs._resolve_ddd_dir(repo_root=repo_root)
    assert result == repo_root / ".canopy" / "ddd"


def test_save_load_with_explicit_ddd_dir(tmp_path, monkeypatch):
    """save(..., ddd_dir=ddd) then load(..., ddd_dir=ddd) round-trips without
    ever calling _resolve_ddd_dir()."""
    import scripts.ddd.runstate as rs
    from scripts.ddd.schemas.models import RunState

    # Make the cwd resolver explode so we prove ddd_dir bypasses it entirely.
    def _boom(*a, **k):
        raise AssertionError("_resolve_ddd_dir should not be called when ddd_dir is passed")

    monkeypatch.setattr(rs, "_resolve_ddd_dir", _boom)

    ddd = tmp_path / "explicit-ddd"
    ddd.mkdir()
    rs.save(RunState(run_id="r-1", narrative_slug="r"), ddd_dir=ddd)
    loaded = rs.load("r-1", ddd_dir=ddd)
    assert loaded.run_id == "r-1"


def test_new_run_with_explicit_ddd_dir(tmp_path, monkeypatch):
    """new_run(..., ddd_dir=ddd) creates the run under the given dir, no resolver."""
    import scripts.ddd.runstate as rs

    def _boom(*a, **k):
        raise AssertionError("_resolve_ddd_dir should not be called when ddd_dir is passed")

    monkeypatch.setattr(rs, "_resolve_ddd_dir", _boom)

    ddd = tmp_path / "explicit-ddd"
    ddd.mkdir()
    run_id = rs.new_run("feat", ddd_dir=ddd)
    assert (ddd / "runs" / run_id / "run_state.yaml").exists()
