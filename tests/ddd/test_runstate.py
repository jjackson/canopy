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
    # Monkeypatch the resolver used by runstate
    import scripts.ddd.runstate as rs
    monkeypatch.setattr(rs, "_resolve_ddd_dir", lambda: ddd_dir)
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
    assert raw["feature"] == "sampling-engine"
    assert raw["schema_version"] == 1


def test_new_run_id_format(tmp_path, monkeypatch):
    _patch_ddd_dir(monkeypatch, tmp_path)

    from scripts.ddd.runstate import new_run

    run_id = new_run("my-feature")
    # Expected pattern: <feature>-<YYYY-MM-DD>-NNN
    assert re.match(r"^my-feature-\d{4}-\d{2}-\d{2}-\d{3}$", run_id), (
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

    run_id = new_run("round-trip-feature")
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
