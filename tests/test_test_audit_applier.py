"""Tests for orchestrator.test_audit.applier — planning and source surgery only.

We do not exercise the git/gh path here (covered manually). These tests verify:
- plan() honors conservative thresholds
- _delete_test removes the right function
- _skip_mark_test inserts the decorator and pytest import
"""
from pathlib import Path

from orchestrator.test_audit.collector import TestItem
from orchestrator.test_audit.parser import StaticAnalysis
from orchestrator.test_audit.runner import TestResult
from orchestrator.test_audit.judge import Verdict
from orchestrator.test_audit.aggregator import aggregate
from orchestrator.test_audit.applier import (
    plan, _delete_test, _skip_mark_test,
)


def _bundle(verdicts_in: dict[str, dict], file: Path):
    items = [TestItem(nodeid=nid, file=file, name=nid.split("::")[-1], line=1)
             for nid in verdicts_in]
    statics = {nid: StaticAnalysis(nodeid=nid, name=nid.split("::")[-1],
                                   body_source="", assertion_count=1)
               for nid in verdicts_in}
    verdicts = {nid: Verdict(nodeid=nid, **payload) for nid, payload in verdicts_in.items()}
    return aggregate(items, statics, {}, verdicts)


def test_plan_skip_marks_env_fragile_regardless_of_score(tmp_path):
    f = tmp_path / "test_x.py"
    f.write_text("def test_a(): pass\n")
    summary = _bundle({
        "test_x.py::test_a": dict(score=8, verdict="prune", reason_code="env-fragile",
                                  reason="missing module"),
    }, f)
    changes = plan(summary, tmp_path)
    assert len(changes) == 1
    assert changes[0].action == "skip"


def test_plan_deletes_only_low_score_prunes_by_default(tmp_path):
    f = tmp_path / "test_x.py"
    f.write_text("def test_a(): pass\ndef test_b(): pass\n")
    summary = _bundle({
        "test_x.py::test_a": dict(score=2, verdict="prune", reason_code="tautology", reason=""),
        "test_x.py::test_b": dict(score=5, verdict="prune", reason_code="weak", reason=""),
    }, f)
    changes = plan(summary, tmp_path)
    assert [c.action for c in changes] == ["delete"]
    assert changes[0].nodeid.endswith("test_a")


def test_plan_aggressive_includes_mid_score_prunes(tmp_path):
    f = tmp_path / "test_x.py"
    f.write_text("def test_a(): pass\ndef test_b(): pass\n")
    summary = _bundle({
        "test_x.py::test_a": dict(score=2, verdict="prune", reason_code="tautology", reason=""),
        "test_x.py::test_b": dict(score=5, verdict="prune", reason_code="weak", reason=""),
    }, f)
    changes = plan(summary, tmp_path, aggressive=True)
    assert sorted(c.nodeid.split("::")[-1] for c in changes) == ["test_a", "test_b"]


def test_plan_never_applies_refactor_or_investigate(tmp_path):
    f = tmp_path / "test_x.py"
    f.write_text("def test_a(): pass\ndef test_b(): pass\n")
    summary = _bundle({
        "test_x.py::test_a": dict(score=3, verdict="refactor", reason_code="unclear", reason=""),
        "test_x.py::test_b": dict(score=2, verdict="investigate", reason_code="failing", reason=""),
    }, f)
    assert plan(summary, tmp_path, aggressive=True) == []


def test_delete_test_removes_function(tmp_path):
    f = tmp_path / "test_x.py"
    f.write_text(
        "def test_keep():\n    assert True\n\n"
        "def test_drop():\n    assert False\n\n"
        "def test_other():\n    assert 1 == 1\n"
    )
    assert _delete_test(f, "test_drop")
    src = f.read_text()
    assert "test_keep" in src
    assert "test_other" in src
    assert "test_drop" not in src


def test_skip_mark_inserts_decorator_and_import(tmp_path):
    f = tmp_path / "test_x.py"
    f.write_text("def test_a():\n    assert 1 == 1\n")
    assert _skip_mark_test(f, "test_a", "missing module foo")
    src = f.read_text()
    assert "import pytest" in src
    assert "@pytest.mark.skip" in src
    assert "missing module foo" in src


def test_skip_mark_idempotent_when_already_skipped(tmp_path):
    f = tmp_path / "test_x.py"
    f.write_text(
        "import pytest\n\n"
        "@pytest.mark.skip(reason='already')\n"
        "def test_a():\n    assert 1 == 1\n"
    )
    before = f.read_text()
    assert _skip_mark_test(f, "test_a", "new reason") is False
    assert f.read_text() == before
