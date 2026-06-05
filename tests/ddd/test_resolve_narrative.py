"""Tests for scripts/ddd/resolve_narrative.py — the no-arg narrative resolver."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

from scripts.ddd.resolve_narrative import resolve


def _write_run(ddd_dir: Path, run_id: str, narrative_slug: str, phase: str, mtime: float) -> None:
    run_dir = ddd_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {"run_id": run_id, "narrative_slug": narrative_slug, "phase": phase}
    f = run_dir / "run_state.yaml"
    f.write_text(yaml.safe_dump(state))
    os.utime(f, (mtime, mtime))


def _write_spec(repo_root: Path, slug: str, mtime: float) -> None:
    specs = repo_root / "docs" / "walkthroughs"
    specs.mkdir(parents=True, exist_ok=True)
    f = specs / f"{slug}.yaml"
    f.write_text("name: x\nnarrative: y\n")
    os.utime(f, (mtime, mtime))


def _init_git_repo(repo_root: Path, branch: str = "main") -> None:
    subprocess.run(["git", "init", "-q", "-b", branch, str(repo_root)], check=True)


class TestExplicit:
    def test_explicit_run_id_resumes(self, tmp_path):
        out = resolve(tmp_path / "ddd", tmp_path, run_id="foo-2026-01-01-001")
        assert out["decision"] == "resume"
        assert out["run_id"] == "foo-2026-01-01-001"
        assert out["confidence"] == "high"

    def test_explicit_feature_resumes_in_progress_run(self, tmp_path):
        ddd = tmp_path / ".canopy" / "ddd"
        _write_run(ddd, "alpha-2026-01-01-001", "alpha", "judged", mtime=1000)
        out = resolve(ddd, tmp_path, narrative_slug="alpha")
        assert out["decision"] == "resume"
        assert out["run_id"] == "alpha-2026-01-01-001"

    def test_explicit_feature_terminal_run_starts_new(self, tmp_path):
        ddd = tmp_path / ".canopy" / "ddd"
        _write_run(ddd, "alpha-2026-01-01-001", "alpha", "uploaded", mtime=1000)
        out = resolve(ddd, tmp_path, narrative_slug="alpha")
        assert out["decision"] == "new"
        assert out["narrative_slug"] == "alpha"


class TestInference:
    def test_picks_most_recent_inflight_run(self, tmp_path):
        ddd = tmp_path / ".canopy" / "ddd"
        _init_git_repo(tmp_path)
        now = 1_000_000.0
        # >6h apart → clear winner, high confidence (not ambiguous).
        _write_run(ddd, "old-2026-01-01-001", "old", "judged", mtime=now - 100_000)
        _write_run(ddd, "new-2026-02-01-001", "newer", "render", mtime=now - 5_000)
        out = resolve(ddd, tmp_path, now=now)
        assert out["decision"] == "resume"
        assert out["narrative_slug"] == "newer"
        assert out["run_id"] == "new-2026-02-01-001"
        assert out["confidence"] == "high"

    def test_terminal_newest_starts_new_run(self, tmp_path):
        ddd = tmp_path / ".canopy" / "ddd"
        _init_git_repo(tmp_path)
        _write_run(ddd, "done-2026-02-01-001", "done", "uploaded", mtime=9000)
        out = resolve(ddd, tmp_path, now=10_000.0)
        assert out["decision"] == "new"
        assert out["narrative_slug"] == "done"

    def test_spec_only_starts_new_run(self, tmp_path):
        ddd = tmp_path / ".canopy" / "ddd"
        _init_git_repo(tmp_path)
        _write_spec(tmp_path, "fresh-narrative_slug", mtime=9000)
        out = resolve(ddd, tmp_path, now=10_000.0)
        assert out["decision"] == "new"
        assert out["narrative_slug"] == "fresh-narrative_slug"
        assert out["spec_path"].endswith("fresh-narrative_slug.yaml")

    def test_close_activity_is_ambiguous(self, tmp_path):
        ddd = tmp_path / ".canopy" / "ddd"
        _init_git_repo(tmp_path)
        _write_run(ddd, "a-2026-02-01-001", "aye", "render", mtime=9000)
        _write_run(ddd, "b-2026-02-01-001", "bee", "render", mtime=9000 + 60)  # 1 min apart
        out = resolve(ddd, tmp_path, now=10_000.0)
        assert out["confidence"] == "ambiguous"
        assert len(out["candidates"]) == 2

    def test_no_candidates_asks(self, tmp_path):
        ddd = tmp_path / ".canopy" / "ddd"
        _init_git_repo(tmp_path)
        out = resolve(ddd, tmp_path, now=10_000.0)
        assert out["decision"] == "ask"
        assert out["confidence"] == "none"

    def test_branch_match_overrides_recency(self, tmp_path):
        """A narrative whose slug matches the current git branch wins even if a
        different narrative was touched more recently."""
        ddd = tmp_path / ".canopy" / "ddd"
        _init_git_repo(tmp_path, branch="emdash/ddd-rooftop-survey-x9")
        # 'rooftop-survey' is older but matches the branch; 'other' is newer.
        now = 10_000.0
        _write_run(ddd, "rooftop-survey-2026-01-01-001", "rooftop-survey", "judged", mtime=now - 3600)
        _write_run(ddd, "other-2026-02-01-001", "other", "render", mtime=now - 60)
        out = resolve(ddd, tmp_path, now=now)
        assert out["narrative_slug"] == "rooftop-survey"
        assert out["confidence"] == "high"
        assert "branch" in out["reason"].lower()

    def test_stale_branch_match_ignored(self, tmp_path):
        """Branch match older than the recency window does NOT override fresher work."""
        ddd = tmp_path / ".canopy" / "ddd"
        _init_git_repo(tmp_path, branch="emdash/ddd-rooftop-survey-x9")
        now = 10_000_000.0
        # rooftop-survey matched the branch but is ancient (> 14 days old).
        _write_run(ddd, "rooftop-survey-2026-01-01-001", "rooftop-survey", "judged", mtime=now - 30 * 24 * 3600)
        _write_run(ddd, "other-2026-02-01-001", "other", "render", mtime=now - 60)
        out = resolve(ddd, tmp_path, now=now)
        assert out["narrative_slug"] == "other"
