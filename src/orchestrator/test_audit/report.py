"""Render audit-report.md, verdicts.yaml, and a one-screen terminal summary."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import yaml

from orchestrator.test_audit.aggregator import AuditSummary


def _verdicts_to_yaml(summary: AuditSummary) -> str:
    payload = {
        "total": summary.total,
        "counts": summary.counts_by_verdict(),
        "verdicts": {nid: asdict(v) for nid, v in summary.verdicts.items()},
        "clusters": [asdict(c) for c in summary.clusters],
        "failing": summary.failing,
        "flaky": summary.flaky,
        "env_fragile": summary.env_fragile,
    }
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)


def _bucket(summary: AuditSummary, verdict: str) -> list[str]:
    out = [nid for nid, v in summary.verdicts.items() if v.verdict == verdict]
    out.sort(key=lambda n: summary.verdicts[n].score)
    return out


def render_report(summary: AuditSummary) -> str:
    lines: list[str] = []
    lines.append("# Test Audit Report")
    lines.append("")
    counts = summary.counts_by_verdict()
    lines.append(
        f"**{summary.total} tests** — "
        f"keep {counts.get('keep', 0)}, "
        f"refactor {counts.get('refactor', 0)}, "
        f"prune {counts.get('prune', 0)}, "
        f"investigate {counts.get('investigate', 0)}."
    )
    if summary.failing:
        lines.append(f"**{len(summary.failing)} failing/erroring** tests in last run.")
    if summary.flaky:
        lines.append(f"**{len(summary.flaky)} flaky** across reruns.")
    if summary.env_fragile:
        lines.append(f"**{len(summary.env_fragile)}** flagged as environment-fragile (will be skip-marked, not deleted).")
    lines.append("")

    def _section(title: str, nodeids: list[str], limit: int = 20) -> None:
        if not nodeids:
            return
        lines.append(f"## {title}")
        lines.append("")
        for nid in nodeids[:limit]:
            v = summary.verdicts.get(nid)
            if not v:
                continue
            lines.append(f"- `{nid}` — score {v.score}, {v.reason_code}: {v.reason}")
        if len(nodeids) > limit:
            lines.append(f"- _...and {len(nodeids) - limit} more (see `verdicts.yaml`)_")
        lines.append("")

    _section("Prune candidates", _bucket(summary, "prune"))
    _section("Refactor candidates", _bucket(summary, "refactor"))
    _section("Investigate (failing or unclear)", _bucket(summary, "investigate"))

    if summary.clusters:
        lines.append("## Redundancy clusters")
        lines.append("")
        for c in summary.clusters[:10]:
            lines.append(f"- **{c.key}** ({len(c.nodeids)} tests)")
            lines.append(f"  - keeper: `{c.keeper}`")
            for nid in c.prune_candidates[:5]:
                lines.append(f"  - prune: `{nid}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_terminal_summary(summary: AuditSummary,
                            applied_pr: str | None = None) -> str:
    """One-screen summary printed to stdout. Tight, scannable."""
    counts = summary.counts_by_verdict()
    lines: list[str] = []
    lines.append(
        f"{summary.total} tests audited: "
        f"keep={counts.get('keep', 0)} "
        f"refactor={counts.get('refactor', 0)} "
        f"prune={counts.get('prune', 0)} "
        f"investigate={counts.get('investigate', 0)}"
    )
    if summary.failing:
        lines.append(f"  failing/erroring: {len(summary.failing)}")
    if summary.flaky:
        lines.append(f"  flaky: {len(summary.flaky)}")
    if summary.env_fragile:
        lines.append(f"  env-fragile: {len(summary.env_fragile)} (will be skip-marked)")

    top = _bucket(summary, "prune")[:5]
    if top:
        lines.append("")
        lines.append("Top prune candidates:")
        for nid in top:
            v = summary.verdicts[nid]
            lines.append(f"  [{v.score}] {nid} — {v.reason_code}: {v.reason}")
    if summary.clusters:
        lines.append("")
        lines.append("Top redundancy clusters:")
        for c in summary.clusters[:3]:
            lines.append(f"  {c.key}: {len(c.nodeids)} tests, keep {c.keeper}")
    if applied_pr:
        lines.append("")
        lines.append(f"Applied changes -> PR: {applied_pr}")
    return "\n".join(lines)


def write_reports(summary: AuditSummary, out_dir: Path) -> dict[str, Path]:
    """Write audit-report.md, verdicts.yaml, summary.md to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    report_md = out_dir / "audit-report.md"
    verdicts_yaml = out_dir / "verdicts.yaml"
    summary_md = out_dir / "summary.md"
    report_md.write_text(render_report(summary), encoding="utf-8")
    verdicts_yaml.write_text(_verdicts_to_yaml(summary), encoding="utf-8")
    summary_md.write_text(render_terminal_summary(summary), encoding="utf-8")
    return {"report": report_md, "verdicts": verdicts_yaml, "summary": summary_md}
