"""Tests for orchestrator.test_audit.runner — junit-xml parsing and parametrize handling."""
import textwrap
from pathlib import Path

from orchestrator.test_audit.runner import _normalize_nodeid, _parse_junit


def test_normalize_nodeid_simple():
    assert _normalize_nodeid("tests.test_foo", "test_bar") == "tests/test_foo.py::test_bar"


def test_normalize_nodeid_with_class():
    nid = _normalize_nodeid("tests.test_foo.TestBar", "test_baz")
    assert nid == "tests/test_foo.py::TestBar::test_baz"


def test_normalize_nodeid_strips_parametrize_suffix():
    """junit-xml emits `name="test_bar[param1]"` for parametrized tests.
    The collector emits `nodeid=test_bar` (no suffix). The runner must
    strip the `[...]` so results match items by base nodeid."""
    nid = _normalize_nodeid("tests.test_foo", "test_bar[param1]")
    assert nid == "tests/test_foo.py::test_bar"


def test_normalize_nodeid_strips_complex_parametrize():
    nid = _normalize_nodeid("tests.test_foo", "test_x[1-True-bar]")
    assert nid == "tests/test_foo.py::test_x"


def test_parse_junit_aggregates_parametrize_results(tmp_path):
    """Multiple <testcase> entries differing only by [param] suffix should
    collapse to a single TestResult per base nodeid. If any param failed,
    the aggregate status is 'failed'; otherwise 'passed'."""
    xml = tmp_path / "junit.xml"
    xml.write_text(textwrap.dedent("""\
        <?xml version="1.0" encoding="utf-8"?>
        <testsuites>
          <testsuite name="pytest" tests="3">
            <testcase classname="tests.test_foo" name="test_x[a]" time="0.01"/>
            <testcase classname="tests.test_foo" name="test_x[b]" time="0.02"/>
            <testcase classname="tests.test_foo" name="test_x[c]" time="0.03">
              <failure message="boom"/>
            </testcase>
          </testsuite>
        </testsuites>
    """))
    results = _parse_junit(xml)
    assert "tests/test_foo.py::test_x" in results
    r = results["tests/test_foo.py::test_x"]
    assert r.status == "failed"
    # Sum of durations across all params.
    assert r.duration_ms >= 60


def test_parse_junit_passing_parametrize_aggregates_to_passed(tmp_path):
    xml = tmp_path / "junit.xml"
    xml.write_text(textwrap.dedent("""\
        <?xml version="1.0" encoding="utf-8"?>
        <testsuites>
          <testsuite name="pytest" tests="2">
            <testcase classname="tests.test_foo" name="test_x[a]" time="0.01"/>
            <testcase classname="tests.test_foo" name="test_x[b]" time="0.02"/>
          </testsuite>
        </testsuites>
    """))
    results = _parse_junit(xml)
    assert results["tests/test_foo.py::test_x"].status == "passed"
