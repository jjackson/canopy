"""Test audit: build a per-test corpus, let the calling agent judge it, then apply.

Public entry: `collect_corpus(repo, ...)` → writes `corpus.yaml`.
                `apply_audit(stamp_dir, ...)` → reads the agent's `verdicts.yaml`.
See `plugins/canopy/skills/test-audit/SKILL.md` for the agent flow.
"""
from orchestrator.test_audit.audit import (
    CollectResult, collect_corpus, apply_audit,
)
from orchestrator.test_audit.collector import TestItem, collect
from orchestrator.test_audit.runner import TestResult, run_pytest
from orchestrator.test_audit.parser import StaticAnalysis, analyze
from orchestrator.test_audit.corpus import build_corpus, write_corpus
from orchestrator.test_audit.applier import (
    Verdict, PlannedChange, ApplyResult,
    plan, apply_verdicts, apply_from_dir,
)
from orchestrator.test_audit.report import render_apply_summary

__all__ = [
    "CollectResult", "collect_corpus", "apply_audit",
    "TestItem", "collect",
    "TestResult", "run_pytest",
    "StaticAnalysis", "analyze",
    "build_corpus", "write_corpus",
    "Verdict", "PlannedChange", "ApplyResult",
    "plan", "apply_verdicts", "apply_from_dir",
    "render_apply_summary",
]
