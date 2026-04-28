"""Apply verdicts: prune (delete) or skip-mark (env-fragile) tests, then open a PR.

Conservative rules (match spec):
  verdict=prune, reason_code=env-fragile  -> add @pytest.mark.skip(...)
  verdict=prune, score <= 3                -> git rm the test
  verdict=prune, score 4-6                 -> only with aggressive=True

`refactor` and `investigate` verdicts are NEVER applied.
"""
from __future__ import annotations

import ast
import logging
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.test_audit.aggregator import AuditSummary

logger = logging.getLogger(__name__)


@dataclass
class PlannedChange:
    nodeid: str
    file: Path
    action: str  # "delete" | "skip"
    reason: str


@dataclass
class ApplyResult:
    changes: list[PlannedChange] = field(default_factory=list)
    branch: str | None = None
    pr_url: str | None = None
    patch_path: Path | None = None
    skipped: list[str] = field(default_factory=list)
    error: str | None = None


def plan(summary: AuditSummary, repo: Path, aggressive: bool = False) -> list[PlannedChange]:
    """Return the list of changes the applier would make."""
    out: list[PlannedChange] = []
    items_by_nodeid = {it.nodeid: it for it in summary.items}
    for nid, v in summary.verdicts.items():
        if v.verdict != "prune":
            continue
        item = items_by_nodeid.get(nid)
        if item is None:
            continue
        if v.reason_code == "env-fragile":
            out.append(PlannedChange(nodeid=nid, file=item.file, action="skip",
                                     reason=v.reason or v.reason_code))
        elif v.score <= 3 or aggressive:
            out.append(PlannedChange(nodeid=nid, file=item.file, action="delete",
                                     reason=v.reason or v.reason_code))
    return out


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _gh_available() -> bool:
    try:
        r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def _delete_test(file: Path, name: str) -> bool:
    """Remove a test function from `file`. Returns True if changed.

    For class-method tests, only the method is removed.
    If removing leaves an empty class or empty file, we leave the empty stub —
    it's the user's problem to clean up after the audit lands.
    """
    src = file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    # Walk top-level + class bodies; find a FunctionDef matching name.
    target_lines: tuple[int, int] | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            start = node.lineno - 1
            end = (getattr(node, "end_lineno", None) or node.lineno) - 1
            # Walk back over decorators.
            for dec in node.decorator_list:
                start = min(start, dec.lineno - 1)
            target_lines = (start, end)
            break
    if target_lines is None:
        return False
    lines = src.splitlines(keepends=True)
    new = lines[: target_lines[0]] + lines[target_lines[1] + 1 :]
    file.write_text("".join(new), encoding="utf-8")
    return True


def _skip_mark_test(file: Path, name: str, reason: str) -> bool:
    """Add `@pytest.mark.skip(reason="...")` decorator to the test function.

    Inserts the import for pytest if missing.
    """
    src = file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False

    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            target = node
            break
    if target is None:
        return False

    # Check for already-skip decorated.
    for dec in target.decorator_list:
        text = ast.unparse(dec) if hasattr(ast, "unparse") else ""
        if "pytest.mark.skip" in text:
            return False  # already skipped, no change

    insert_line = target.lineno - 1  # 0-indexed line of `def ...`
    # Get indentation of def line.
    lines = src.splitlines(keepends=True)
    def_line = lines[insert_line]
    indent = re.match(r"\s*", def_line).group(0)

    # Sanitize the reason — keep it short and safe in a string literal.
    safe_reason = (reason or "audit: env-fragile").replace('"', "'")[:140]
    decorator = f'{indent}@pytest.mark.skip(reason="audit: {safe_reason}")\n'
    lines.insert(insert_line, decorator)

    new_src = "".join(lines)
    if "import pytest" not in new_src:
        # Add it at the top after any module docstring.
        try:
            tree2 = ast.parse(new_src)
            insert_at = 0
            if (tree2.body and isinstance(tree2.body[0], ast.Expr)
                    and isinstance(tree2.body[0].value, ast.Constant)
                    and isinstance(tree2.body[0].value.value, str)):
                insert_at = (tree2.body[0].end_lineno or 1)
            lines2 = new_src.splitlines(keepends=True)
            lines2.insert(insert_at, "import pytest\n")
            new_src = "".join(lines2)
        except SyntaxError:
            pass

    file.write_text(new_src, encoding="utf-8")
    return True


def apply_verdicts(summary: AuditSummary, repo: Path,
                   aggressive: bool = False, dry_run: bool = False,
                   branch_prefix: str = "test-audit") -> ApplyResult:
    """Plan + execute changes. Open a PR (or write a patch file if gh is missing)."""
    changes = plan(summary, repo, aggressive=aggressive)
    res = ApplyResult(changes=changes)
    if not changes:
        return res
    if dry_run:
        return res

    # Group by file for fewer reads/writes.
    by_file: dict[Path, list[PlannedChange]] = {}
    for c in changes:
        by_file.setdefault(c.file, []).append(c)

    for file, file_changes in by_file.items():
        # Apply deletions before skips (deletions remove fewer lines later).
        for c in [x for x in file_changes if x.action == "delete"]:
            name = c.nodeid.split("::")[-1]
            if not _delete_test(file, name):
                res.skipped.append(c.nodeid)
        for c in [x for x in file_changes if x.action == "skip"]:
            name = c.nodeid.split("::")[-1]
            if not _skip_mark_test(file, name, c.reason):
                res.skipped.append(c.nodeid)

    # Stage and commit on a branch.
    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    branch = f"{branch_prefix}/{stamp}"
    res.branch = branch

    git_status = _git("status", "--porcelain", cwd=repo)
    if not git_status.stdout.strip():
        return res  # nothing changed (all deletes failed silently)

    cur = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo).stdout.strip()
    _git("checkout", "-b", branch, cwd=repo)
    _git("add", "-A", cwd=repo)
    body = (
        f"Test audit: {len([c for c in changes if c.action=='delete'])} deletions, "
        f"{len([c for c in changes if c.action=='skip'])} skip-marks. "
        "See PR body for the full report."
    )
    _git("commit", "-m", body, cwd=repo)

    if _gh_available():
        push = _git("push", "-u", "origin", branch, cwd=repo)
        if push.returncode != 0:
            res.error = f"git push failed: {push.stderr[:200]}"
            return res
        # Use the audit-report.md from .canopy/test-audits/ as the PR body, if present.
        latest_report = None
        audits_dir = repo / ".canopy" / "test-audits"
        if audits_dir.exists():
            stamps = sorted(audits_dir.iterdir(), reverse=True)
            if stamps:
                cand = stamps[0] / "audit-report.md"
                if cand.exists():
                    latest_report = cand
        body_arg = ["--body", body]
        if latest_report:
            body_arg = ["--body-file", str(latest_report)]
        pr = subprocess.run(
            ["gh", "pr", "create", "--title", f"test-audit: {stamp}", *body_arg],
            cwd=repo, capture_output=True, text=True,
        )
        if pr.returncode == 0:
            # gh prints the URL on the last line of stdout.
            url = pr.stdout.strip().splitlines()[-1] if pr.stdout.strip() else ""
            res.pr_url = url
        else:
            res.error = f"gh pr create failed: {pr.stderr[:200]}"
    else:
        # No gh: emit a patch file the user can apply manually.
        patch = subprocess.run(["git", "format-patch", "-1", "--stdout"],
                               cwd=repo, capture_output=True, text=True)
        patch_path = repo / ".canopy" / "test-audits" / f"{stamp}.patch"
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(patch.stdout, encoding="utf-8")
        res.patch_path = patch_path

    # Restore the user's prior branch so they're not stuck on the audit branch.
    _git("checkout", cur, cwd=repo)
    return res
