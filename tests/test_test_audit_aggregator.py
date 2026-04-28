"""Tests for orchestrator.test_audit.aggregator clustering and bucketing."""
from pathlib import Path

from orchestrator.test_audit.collector import TestItem
from orchestrator.test_audit.parser import StaticAnalysis
from orchestrator.test_audit.runner import TestResult
from orchestrator.test_audit.judge import Verdict
from orchestrator.test_audit.aggregator import aggregate


def _item(nid):
    return TestItem(nodeid=nid, file=Path("/tmp/x.py"), name=nid.split("::")[-1], line=1)


def _static(nid, funcs, asserts=2):
    return StaticAnalysis(
        nodeid=nid, name=nid.split("::")[-1], body_source="...",
        assertion_count=asserts, source_funcs_referenced=funcs,
        line_count=5,
    )


def _verdict(nid, verdict, score, reason_code="ok"):
    return Verdict(nodeid=nid, score=score, verdict=verdict,
                   reason_code=reason_code, reason="")


def test_clusters_group_tests_exercising_same_funcs():
    items = [_item("a::t1"), _item("a::t2"), _item("a::t3")]
    statics = {
        "a::t1": _static("a::t1", ["foo"]),
        "a::t2": _static("a::t2", ["foo"]),
        "a::t3": _static("a::t3", ["bar"]),
    }
    verdicts = {
        "a::t1": _verdict("a::t1", "keep", 8),
        "a::t2": _verdict("a::t2", "keep", 5),
        "a::t3": _verdict("a::t3", "keep", 7),
    }
    summary = aggregate(items, statics, {}, verdicts)
    assert len(summary.clusters) == 1
    cluster = summary.clusters[0]
    assert sorted(cluster.nodeids) == ["a::t1", "a::t2"]
    assert cluster.keeper == "a::t1"  # higher score
    assert cluster.prune_candidates == ["a::t2"]


def test_failing_and_flaky_buckets_populated():
    items = [_item("a::t1"), _item("a::t2")]
    statics = {nid: _static(nid, []) for nid in ["a::t1", "a::t2"]}
    verdicts = {nid: _verdict(nid, "keep", 8) for nid in ["a::t1", "a::t2"]}
    runtimes = {
        "a::t1": TestResult(nodeid="a::t1", status="failed", duration_ms=10),
        "a::t2": TestResult(nodeid="a::t2", status="passed", duration_ms=10, flake_count=2),
    }
    summary = aggregate(items, statics, runtimes, verdicts)
    assert summary.failing == ["a::t1"]
    assert summary.flaky == ["a::t2"]


def test_top_prunes_sorted_worst_first():
    items = [_item("a::lo"), _item("a::hi"), _item("a::keep")]
    statics = {nid: _static(nid, []) for nid in ["a::lo", "a::hi", "a::keep"]}
    verdicts = {
        "a::lo": _verdict("a::lo", "prune", 1),
        "a::hi": _verdict("a::hi", "prune", 5),
        "a::keep": _verdict("a::keep", "keep", 9),
    }
    summary = aggregate(items, statics, {}, verdicts)
    assert summary.top_prunes == ["a::lo", "a::hi"]


def test_env_fragile_collected():
    items = [_item("a::t1")]
    statics = {"a::t1": _static("a::t1", [])}
    verdicts = {"a::t1": _verdict("a::t1", "prune", 2, reason_code="env-fragile")}
    summary = aggregate(items, statics, {}, verdicts)
    assert summary.env_fragile == ["a::t1"]
