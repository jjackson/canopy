"""Tests for orchestrator.test_audit.collector."""
from pathlib import Path

from orchestrator.test_audit.collector import collect


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_suite"


def test_collect_finds_all_test_functions():
    items = collect(FIXTURE)
    names = sorted(it.name for it in items)
    assert names == sorted([
        "test_add_returns_sum",
        "test_add_with_negatives",
        "test_always_passes",
        "test_no_assertion",
        "test_env_fragile",
        "test_subtraction_works",
        "test_add_with_mock_of_cut",
    ])


def test_collect_nodeid_includes_relative_file_path():
    items = collect(FIXTURE)
    item = next(it for it in items if it.name == "test_add_returns_sum")
    assert item.nodeid.endswith("test_calculator.py::test_add_returns_sum")


def test_collect_skips_non_test_files(tmp_path):
    (tmp_path / "main.py").write_text("def foo(): pass\ndef test_x(): pass\n")
    (tmp_path / "test_real.py").write_text("def test_real(): assert True\n")
    items = collect(tmp_path)
    assert [it.name for it in items] == ["test_real"]
