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


def test_pytest_raises_counts_as_real_assertion(tmp_path):
    """`with pytest.raises(...)` is a meaningful assertion — must set
    has_real_assertion=True even with no `assert` statement."""
    f = tmp_path / "test_x.py"
    f.write_text(
        "import pytest\n"
        "def divide(a, b): return a // b\n\n"
        "def test_divide_by_zero_raises():\n"
        "    with pytest.raises(ZeroDivisionError):\n"
        "        divide(1, 0)\n"
    )
    from orchestrator.test_audit.collector import TestItem
    item = TestItem(nodeid="test_x.py::test_divide_by_zero_raises",
                    file=f, name="test_divide_by_zero_raises", line=4)
    static = analyze(item)
    assert static.has_real_assertion is True
    assert static.assertion_count >= 1


def test_pytest_raises_with_match_counts_as_real_assertion(tmp_path):
    """`pytest.raises(..., match='...')` is the strongest exception assertion."""
    f = tmp_path / "test_x.py"
    f.write_text(
        "import pytest\n"
        "def parse(s): raise ValueError('bad')\n\n"
        "def test_parse_rejects_garbage():\n"
        "    with pytest.raises(ValueError, match='bad'):\n"
        "        parse('garbage')\n"
    )
    from orchestrator.test_audit.collector import TestItem
    item = TestItem(nodeid="test_x.py::test_parse_rejects_garbage",
                    file=f, name="test_parse_rejects_garbage", line=4)
    static = analyze(item)
    assert static.has_real_assertion is True


def test_bare_pytest_raises_call_counts_too(tmp_path):
    """Some codebases use pytest.raises() outside a `with` block (less common)."""
    f = tmp_path / "test_x.py"
    f.write_text(
        "import pytest\n"
        "def explode(): raise RuntimeError\n\n"
        "def test_explode():\n"
        "    pytest.raises(RuntimeError, explode)\n"
    )
    from orchestrator.test_audit.collector import TestItem
    item = TestItem(nodeid="test_x.py::test_explode", file=f, name="test_explode", line=4)
    static = analyze(item)
    assert static.has_real_assertion is True
