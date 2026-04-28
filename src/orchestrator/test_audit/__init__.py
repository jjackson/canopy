"""Test audit: score each pytest test on 'is it pulling its weight'.

Public entry: `run_audit(repo, ...)` — full pipeline.
See `cli.py` `test_audit` command for the user-facing wrapper.
"""
from orchestrator.test_audit.audit import run_audit, AuditConfig, AuditResult
from orchestrator.test_audit.collector import TestItem, collect
from orchestrator.test_audit.runner import TestResult, run_pytest
from orchestrator.test_audit.parser import StaticAnalysis, analyze
from orchestrator.test_audit.judge import Verdict, judge_one, judge_all
from orchestrator.test_audit.aggregator import (
    AuditSummary, RedundancyCluster, aggregate,
)
from orchestrator.test_audit.report import write_reports, render_terminal_summary
from orchestrator.test_audit.applier import apply_verdicts, ApplyResult

__all__ = [
    "run_audit", "AuditConfig", "AuditResult",
    "TestItem", "collect",
    "TestResult", "run_pytest",
    "StaticAnalysis", "analyze",
    "Verdict", "judge_one", "judge_all",
    "AuditSummary", "RedundancyCluster", "aggregate",
    "write_reports", "render_terminal_summary",
    "apply_verdicts", "ApplyResult",
]
