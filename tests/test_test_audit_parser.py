"""Tests for orchestrator.test_audit.parser AST extraction."""
from pathlib import Path

from orchestrator.test_audit.collector import collect
from orchestrator.test_audit.parser import analyze


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_suite"


def _by_name(items, name):
    return next(it for it in items if it.name == name)


def test_assertion_count_zero_when_no_asserts():
    items = collect(FIXTURE)
    static = analyze(_by_name(items, "test_no_assertion"))
    assert static.assertion_count == 0
    assert static.has_real_assertion is False


def test_tautology_assertion_counted_but_not_real():
    items = collect(FIXTURE)
    static = analyze(_by_name(items, "test_always_passes"))
    assert static.assertion_count == 1
    assert static.has_real_assertion is False  # `assert True` is a Constant


def test_real_assertion_flagged():
    items = collect(FIXTURE)
    static = analyze(_by_name(items, "test_add_returns_sum"))
    assert static.assertion_count == 1
    assert static.has_real_assertion is True


def test_mock_targets_extracted():
    items = collect(FIXTURE)
    static = analyze(_by_name(items, "test_add_with_mock_of_cut"))
    assert any("add" in t for t in static.mock_targets)


def test_source_funcs_referenced_picks_up_cut():
    items = collect(FIXTURE)
    static = analyze(_by_name(items, "test_add_returns_sum"))
    assert "add" in static.source_funcs_referenced
