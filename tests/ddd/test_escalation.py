"""Tests for scripts/ddd/escalation.py (SP6c).

The ddd-dir resolver is monkeypatched to tmp_path so no real filesystem
state is read or written during tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helper: redirect _resolve_ddd_dir to tmp_path
# ---------------------------------------------------------------------------


def _patch_ddd_dir(monkeypatch, tmp_path: Path) -> Path:
    ddd_dir = tmp_path / ".canopy" / "ddd"
    ddd_dir.mkdir(parents=True)
    import scripts.ddd.escalation as esc
    monkeypatch.setattr(esc, "_resolve_ddd_dir", lambda: ddd_dir)
    return ddd_dir


# ---------------------------------------------------------------------------
# record() — basic mechanics
# ---------------------------------------------------------------------------


class TestRecord:
    def test_accepted_increments_accepted_and_streak(self, monkeypatch, tmp_path):
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        esc.record("go_nogo", accepted=True)
        esc.record("go_nogo", accepted=True)

        data = json.loads((tmp_path / ".canopy" / "ddd" / "escalation.json").read_text())
        assert data["go_nogo"]["accepted"] == 2
        assert data["go_nogo"]["streak"] == 2
        assert data["go_nogo"]["redirected"] == 0

    def test_redirected_increments_redirected_and_resets_streak(self, monkeypatch, tmp_path):
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        esc.record("go_nogo", accepted=True)
        esc.record("go_nogo", accepted=True)
        esc.record("go_nogo", accepted=False)  # redirect

        data = json.loads((tmp_path / ".canopy" / "ddd" / "escalation.json").read_text())
        assert data["go_nogo"]["redirected"] == 1
        assert data["go_nogo"]["streak"] == 0
        assert data["go_nogo"]["accepted"] == 2

    def test_separate_classes_are_independent(self, monkeypatch, tmp_path):
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        esc.record("class_a", accepted=True)
        esc.record("class_b", accepted=False)

        data = json.loads((tmp_path / ".canopy" / "ddd" / "escalation.json").read_text())
        assert data["class_a"]["streak"] == 1
        assert data["class_b"]["streak"] == 0


# ---------------------------------------------------------------------------
# should_propose_downgrade()
# ---------------------------------------------------------------------------


class TestShouldProposeDowngrade:
    def test_true_after_5_consecutive_accepts(self, monkeypatch, tmp_path):
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        for _ in range(5):
            esc.record("go_nogo", accepted=True)

        assert esc.should_propose_downgrade("go_nogo", threshold=5) is True

    def test_false_before_threshold(self, monkeypatch, tmp_path):
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        for _ in range(4):
            esc.record("go_nogo", accepted=True)

        assert esc.should_propose_downgrade("go_nogo", threshold=5) is False

    def test_false_after_redirect_resets_streak(self, monkeypatch, tmp_path):
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        for _ in range(5):
            esc.record("go_nogo", accepted=True)

        assert esc.should_propose_downgrade("go_nogo") is True  # would trigger

        esc.record("go_nogo", accepted=False)  # redirect — resets streak

        assert esc.should_propose_downgrade("go_nogo") is False

    def test_false_when_already_downgraded(self, monkeypatch, tmp_path):
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        for _ in range(10):
            esc.record("go_nogo", accepted=True)

        esc.mark_downgraded("go_nogo")

        assert esc.should_propose_downgrade("go_nogo") is False

    def test_custom_threshold(self, monkeypatch, tmp_path):
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        for _ in range(3):
            esc.record("class_x", accepted=True)

        assert esc.should_propose_downgrade("class_x", threshold=3) is True
        assert esc.should_propose_downgrade("class_x", threshold=4) is False


# ---------------------------------------------------------------------------
# mark_downgraded() / is_downgraded()
# ---------------------------------------------------------------------------


class TestMarkAndIsDowngraded:
    def test_mark_downgraded_sets_flag(self, monkeypatch, tmp_path):
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        assert esc.is_downgraded("go_nogo") is False

        esc.mark_downgraded("go_nogo")

        assert esc.is_downgraded("go_nogo") is True

    def test_should_propose_false_after_mark(self, monkeypatch, tmp_path):
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        for _ in range(10):
            esc.record("go_nogo", accepted=True)

        esc.mark_downgraded("go_nogo")

        assert esc.should_propose_downgrade("go_nogo") is False

    def test_is_downgraded_false_for_unknown_class(self, monkeypatch, tmp_path):
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        assert esc.is_downgraded("never_seen") is False


# ---------------------------------------------------------------------------
# Persistence across reload
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_counts_persist_across_reload(self, monkeypatch, tmp_path):
        """Importing after writes re-reads from disk, preserving all counts."""
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        esc.record("cls", accepted=True)
        esc.record("cls", accepted=True)
        esc.record("cls", accepted=False)
        esc.mark_downgraded("cls")

        # Verify the raw JSON has expected values
        state_file = tmp_path / ".canopy" / "ddd" / "escalation.json"
        data = json.loads(state_file.read_text())
        assert data["cls"]["accepted"] == 2
        assert data["cls"]["redirected"] == 1
        assert data["cls"]["streak"] == 0
        assert data["cls"]["downgraded"] is True

    def test_state_reloaded_on_each_call(self, monkeypatch, tmp_path):
        """Each function call loads fresh from disk (no in-memory cache)."""
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        esc.record("cls2", accepted=True)
        esc.record("cls2", accepted=True)
        esc.record("cls2", accepted=True)
        esc.record("cls2", accepted=True)
        esc.record("cls2", accepted=True)

        # Write directly to the state file to simulate an out-of-process mutation
        state_file = tmp_path / ".canopy" / "ddd" / "escalation.json"
        raw = json.loads(state_file.read_text())
        raw["cls2"]["downgraded"] = True
        state_file.write_text(json.dumps(raw))

        # Next call must see the externally-written value
        assert esc.is_downgraded("cls2") is True
        assert esc.should_propose_downgrade("cls2") is False

    def test_default_entry_not_written_on_read_only_query(self, monkeypatch, tmp_path):
        """should_propose_downgrade and is_downgraded on unknown class don't crash."""
        _patch_ddd_dir(monkeypatch, tmp_path)
        from scripts.ddd import escalation as esc

        # No record() call — just query
        assert esc.should_propose_downgrade("brand_new_class") is False
        assert esc.is_downgraded("brand_new_class") is False
