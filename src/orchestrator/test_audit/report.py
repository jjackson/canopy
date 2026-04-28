"""Render a one-screen terminal summary for the apply CLI.

The full audit-report.md is written by the calling agent, not by this module.
"""
from __future__ import annotations

from orchestrator.test_audit.applier import ApplyResult


def render_apply_summary(result: ApplyResult) -> str:
    deletes = sum(1 for c in result.changes if c.action == "delete")
    skips = sum(1 for c in result.changes if c.action == "skip")
    lines = [f"Applied {len(result.changes)} changes: {deletes} deletions, {skips} skip-marks"]
    if result.skipped:
        lines.append(f"  {len(result.skipped)} planned changes failed (test not found in source)")
    if result.branch:
        lines.append(f"  branch: {result.branch}")
    if result.pr_url:
        lines.append(f"  PR: {result.pr_url}")
    elif result.patch_path:
        lines.append(f"  patch (gh not available): {result.patch_path}")
    if result.error:
        lines.append(f"  error: {result.error}")
    return "\n".join(lines)
