"""Tests for orchestrator.test_audit.judge YAML parsing and parallel dispatch.

We never call `claude -p` from tests — `invoke` is stubbed.
"""
from pathlib import Path

from orchestrator.test_audit.collector import TestItem
from orchestrator.test_audit.parser import StaticAnalysis
from orchestrator.test_audit.runner import TestResult
from orchestrator.test_audit.judge import judge_one, judge_all, _parse_verdict


def _stub_response(score=8, verdict="keep", reason_code="ok", reason="fine"):
    return f"""
```yaml
score: {score}
verdict: {verdict}
reason_code: {reason_code}
reason: {reason}
dimensions:
  meaningful_assertion: 8
  behavior_vs_implementation: 7
  mock_discipline: 9
  name_match: 8
  clarity: 7
```
"""


def _item(nid="t.py::test_x"):
    return TestItem(nodeid=nid, file=Path("/tmp/t.py"), name="test_x", line=1)


def _static(nid="t.py::test_x"):
    return StaticAnalysis(nodeid=nid, name="test_x", body_source="def test_x(): pass",
                          assertion_count=0)


def test_parse_verdict_extracts_yaml_block():
    v = _parse_verdict("t::x", _stub_response(score=4, verdict="prune",
                                              reason_code="weak", reason="meh"))
    assert v.score == 4
    assert v.verdict == "prune"
    assert v.reason_code == "weak"
    assert v.dimensions["clarity"] == 7


def test_parse_verdict_falls_back_to_investigate_on_invalid_verdict():
    raw = "```yaml\nscore: 2\nverdict: ???\nreason_code: bad\nreason: x\n```"
    v = _parse_verdict("t::x", raw)
    assert v.verdict == "investigate"


def test_parse_verdict_handles_garbled_yaml():
    v = _parse_verdict("t::x", "definitely not yaml: : :")
    assert v.verdict == "investigate"
    assert v.reason_code in ("parse-error", "unknown")


def test_judge_one_uses_invoke_override():
    invoked = []

    def fake(prompt: str) -> str:
        invoked.append(prompt)
        return _stub_response(score=9)

    v = judge_one(_item(), _static(), None, invoke=fake)
    assert len(invoked) == 1
    assert v.score == 9
    assert v.verdict == "keep"


def test_judge_all_runs_in_parallel_with_stub():
    items = [_item(f"t.py::test_{i}") for i in range(5)]
    statics = {it.nodeid: StaticAnalysis(nodeid=it.nodeid, name=it.name,
                                          body_source="", assertion_count=0)
               for it in items}
    runtimes = {}

    def fake(_prompt):
        return _stub_response()

    verdicts = judge_all(items, statics, runtimes, invoke=fake, parallelism=3)
    assert set(verdicts.keys()) == {it.nodeid for it in items}
    assert all(v.verdict == "keep" for v in verdicts.values())


def test_judge_all_records_judge_errors():
    items = [_item("t.py::test_a")]
    statics = {"t.py::test_a": StaticAnalysis(nodeid="t.py::test_a", name="test_a",
                                              body_source="", assertion_count=0)}

    def fake(_p):
        raise RuntimeError("boom")

    verdicts = judge_all(items, statics, {}, invoke=fake)
    v = verdicts["t.py::test_a"]
    assert v.verdict == "investigate"
    assert v.reason_code == "judge-error"
    assert "boom" in (v.reason or "")
