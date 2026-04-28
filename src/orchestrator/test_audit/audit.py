"""End-to-end pipeline glue: collect -> run -> parse -> judge -> aggregate -> report -> apply."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from orchestrator.test_audit.collector import collect
from orchestrator.test_audit.runner import run_pytest
from orchestrator.test_audit.parser import analyze
from orchestrator.test_audit.judge import judge_all
from orchestrator.test_audit.aggregator import aggregate, AuditSummary
from orchestrator.test_audit.report import write_reports, render_terminal_summary
from orchestrator.test_audit.applier import apply_verdicts, ApplyResult

logger = logging.getLogger(__name__)


@dataclass
class AuditConfig:
    repo: Path
    run_tests: bool = True
    reruns: int = 0
    scope: str = "all"  # all | changed
    apply: bool = True  # default mode-C per design
    aggressive: bool = False
    parallelism: int = 4
    judge_model: str = "haiku"
    invoke_override: Callable[[str], str] | None = None  # for tests


@dataclass
class AuditResult:
    summary: AuditSummary
    out_dir: Path
    files: dict[str, Path] = field(default_factory=dict)
    apply_result: ApplyResult | None = None


def run_audit(config: AuditConfig) -> AuditResult:
    repo = config.repo.resolve()
    items = collect(repo, scope=config.scope)
    statics = {it.nodeid: analyze(it) for it in items}

    runtimes = {}
    if config.run_tests:
        runtimes = run_pytest(repo, reruns=config.reruns)

    verdicts = judge_all(
        items, statics, runtimes,
        invoke=config.invoke_override,
        parallelism=config.parallelism,
        model=config.judge_model,
    )

    summary = aggregate(items, statics, runtimes, verdicts)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = repo / ".canopy" / "test-audits" / stamp
    files = write_reports(summary, out_dir)

    apply_result: ApplyResult | None = None
    if config.apply:
        apply_result = apply_verdicts(summary, repo, aggressive=config.aggressive)

    return AuditResult(summary=summary, out_dir=out_dir, files=files,
                       apply_result=apply_result)
