"""Aggregate per-test verdicts into a summary; detect redundancy across siblings."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from orchestrator.test_audit.collector import TestItem
from orchestrator.test_audit.parser import StaticAnalysis
from orchestrator.test_audit.runner import TestResult
from orchestrator.test_audit.judge import Verdict


@dataclass
class RedundancyCluster:
    key: str  # human-readable cluster signature
    nodeids: list[str]
    keeper: str  # the nodeid we suggest keeping (highest verdict score)
    prune_candidates: list[str]  # the others


@dataclass
class AuditSummary:
    items: list[TestItem]
    statics: dict[str, StaticAnalysis]
    runtimes: dict[str, TestResult]
    verdicts: dict[str, Verdict]
    clusters: list[RedundancyCluster] = field(default_factory=list)
    failing: list[str] = field(default_factory=list)
    flaky: list[str] = field(default_factory=list)
    env_fragile: list[str] = field(default_factory=list)
    top_prunes: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.items)

    def counts_by_verdict(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for v in self.verdicts.values():
            out[v.verdict] += 1
        return dict(out)


def _cluster_key(static: StaticAnalysis) -> str:
    # Cluster on which functions are exercised + assertion-count bucket.
    if not static.source_funcs_referenced:
        return ""  # don't cluster tests with no identified CUT
    funcs = ",".join(static.source_funcs_referenced[:5])
    bucket = "lo" if static.assertion_count <= 1 else ("mid" if static.assertion_count <= 3 else "hi")
    return f"{funcs}|{bucket}"


def _find_clusters(statics: dict[str, StaticAnalysis],
                   verdicts: dict[str, Verdict]) -> list[RedundancyCluster]:
    by_key: dict[str, list[str]] = defaultdict(list)
    for nid, st in statics.items():
        key = _cluster_key(st)
        if key:
            by_key[key].append(nid)
    clusters: list[RedundancyCluster] = []
    for key, members in by_key.items():
        if len(members) < 2:
            continue
        # Pick keeper: highest score, breaking ties by line count (more comprehensive).
        def _rank(nid: str) -> tuple[int, int]:
            v = verdicts.get(nid)
            score = v.score if v else 0
            lines = statics[nid].line_count
            return (score, lines)
        ordered = sorted(members, key=_rank, reverse=True)
        keeper = ordered[0]
        rest = ordered[1:]
        clusters.append(RedundancyCluster(
            key=key, nodeids=members, keeper=keeper, prune_candidates=rest,
        ))
    # Largest clusters first.
    clusters.sort(key=lambda c: -len(c.nodeids))
    return clusters


def aggregate(items: list[TestItem],
              statics: dict[str, StaticAnalysis],
              runtimes: dict[str, TestResult],
              verdicts: dict[str, Verdict]) -> AuditSummary:
    failing = [nid for nid, r in runtimes.items() if r.status in ("failed", "error")]
    flaky = [nid for nid, r in runtimes.items() if r.flake_count > 0]
    env_fragile = [nid for nid, v in verdicts.items() if v.reason_code == "env-fragile"]

    clusters = _find_clusters(statics, verdicts)

    # top_prunes: verdict=prune, sorted by ascending score (worst first).
    prunes = [nid for nid, v in verdicts.items() if v.verdict == "prune"]
    prunes.sort(key=lambda n: verdicts[n].score)

    return AuditSummary(
        items=items, statics=statics, runtimes=runtimes, verdicts=verdicts,
        clusters=clusters, failing=failing, flaky=flaky,
        env_fragile=env_fragile, top_prunes=prunes,
    )
