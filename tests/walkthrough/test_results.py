"""Unit tests for ActionResult + RunReport."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib.results import (  # noqa: E402
    ActionAssertError,
    ActionResult,
    RunReport,
)


def test_action_result_ok_defaults():
    r = ActionResult(kind="click", ok=True)
    assert r.ok is True
    assert r.error_kind is None
    assert r.error_message is None


def test_run_report_summary_empty():
    assert RunReport().summary() == "0 actions"


def test_run_report_summary_all_ok():
    rep = RunReport()
    rep.record(ActionResult(kind="click", ok=True))
    rep.record(ActionResult(kind="fill", ok=True))
    assert rep.summary() == "2 actions: all ok"


def test_run_report_summary_mixed():
    rep = RunReport()
    rep.record(ActionResult(kind="click", ok=True))
    rep.record(ActionResult(kind="click", ok=False, target="Foo", error_kind="target_not_found"))
    rep.record(ActionResult(kind="fill", ok=False, error_kind="playwright"))
    assert rep.summary() == "3 actions: 1 ok, 2 failed"
    failures = rep.failures()
    assert len(failures) == 2
    assert failures[0].target == "Foo"


def test_run_report_to_json_roundtrips():
    rep = RunReport()
    rep.record(ActionResult(kind="click", ok=True, target="Buy", elapsed_ms=42))
    rep.record(ActionResult(kind="fill", ok=False, error_kind="target_not_found",
                            error_message="not visible"))
    parsed = json.loads(rep.to_json())
    assert parsed["total"] == 2
    assert parsed["ok"] == 1
    assert parsed["failed"] == 1
    assert parsed["actions"][0]["kind"] == "click"
    assert parsed["actions"][1]["error_kind"] == "target_not_found"


def test_action_assert_error_is_runtime_error():
    # Subclass relationship matters: callers `except RuntimeError` should catch.
    assert issubclass(ActionAssertError, RuntimeError)
