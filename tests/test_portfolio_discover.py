"""Tests for src/orchestrator/portfolio_discover.py."""
import os
import subprocess
from pathlib import Path

import pytest

from orchestrator.portfolio_discover import (
    diff_against_curated,
    discover_active_repos,
)


def _make_repo(path: Path, days_old: int = 0) -> None:
    """Initialize a git repo with one commit; optionally back-date the commit."""
    path.mkdir(parents=True)
    subprocess.check_call(["git", "init", "-q", "-b", "main"], cwd=path)
    subprocess.check_call(["git", "config", "user.email", "t@t"], cwd=path)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=path)
    (path / "README.md").write_text("test\n")
    subprocess.check_call(["git", "add", "."], cwd=path)
    env = {**os.environ}
    if days_old > 0:
        from datetime import datetime, timedelta, timezone
        ts = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
        env["GIT_AUTHOR_DATE"] = ts
        env["GIT_COMMITTER_DATE"] = ts
    subprocess.check_call(
        ["git", "commit", "-q", "-m", "init"],
        cwd=path,
        env=env,
    )


class TestDiscoverActiveRepos:
    def test_finds_recent_repo(self, tmp_path: Path) -> None:
        _make_repo(tmp_path / "myproj")
        result = discover_active_repos(roots=[tmp_path], max_age_days=30)
        assert len(result) == 1
        assert result[0]["slug"] == "myproj"
        assert result[0]["path"] == str(tmp_path / "myproj")
        assert result[0]["last_commit"]  # ISO timestamp populated

    def test_skips_old_repo(self, tmp_path: Path) -> None:
        _make_repo(tmp_path / "old", days_old=60)
        result = discover_active_repos(roots=[tmp_path], max_age_days=30)
        assert result == []

    def test_skips_non_git_dir(self, tmp_path: Path) -> None:
        (tmp_path / "notarepo").mkdir()
        (tmp_path / "notarepo" / "file.txt").write_text("x")
        result = discover_active_repos(roots=[tmp_path], max_age_days=30)
        assert result == []

    def test_skips_files(self, tmp_path: Path) -> None:
        (tmp_path / "afile.txt").write_text("x")
        result = discover_active_repos(roots=[tmp_path], max_age_days=30)
        assert result == []

    def test_skips_dotted_dirs(self, tmp_path: Path) -> None:
        # `.cache` and similar shouldn't ever count even if they contain a .git
        _make_repo(tmp_path / ".cache" / "weird-but-valid-repo")
        result = discover_active_repos(roots=[tmp_path / ".cache"], max_age_days=30)
        # The root itself is .cache; we skip the children with leading dots.
        # Confirm nothing comes back when we point AT a valid root and the
        # repo lives under a dotted child.
        result2 = discover_active_repos(roots=[tmp_path], max_age_days=30)
        assert result2 == []  # tmp_path's only child is .cache, which is skipped

    def test_dedups_by_slug_across_roots(self, tmp_path: Path) -> None:
        a = tmp_path / "rootA"
        b = tmp_path / "rootB"
        _make_repo(a / "myproj")
        _make_repo(b / "myproj")
        result = discover_active_repos(roots=[a, b], max_age_days=30)
        assert len(result) == 1
        assert result[0]["slug"] == "myproj"
        # First root wins
        assert "rootA" in result[0]["path"]

    def test_handles_missing_roots(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent"
        result = discover_active_repos(roots=[nonexistent], max_age_days=30)
        assert result == []

    def test_sorts_newest_first(self, tmp_path: Path) -> None:
        _make_repo(tmp_path / "older", days_old=10)
        _make_repo(tmp_path / "newer")
        result = discover_active_repos(roots=[tmp_path], max_age_days=30)
        assert len(result) == 2
        assert result[0]["slug"] == "newer"
        assert result[1]["slug"] == "older"


class TestDiffAgainstCurated:
    def test_filters_curated(self) -> None:
        active = [
            {"slug": "a", "path": "/a"},
            {"slug": "b", "path": "/b"},
            {"slug": "c", "path": "/c"},
        ]
        result = diff_against_curated(active, {"a", "b"})
        assert [r["slug"] for r in result] == ["c"]

    def test_empty_curated_returns_all(self) -> None:
        active = [{"slug": "a"}, {"slug": "b"}]
        result = diff_against_curated(active, set())
        assert result == active

    def test_empty_active_returns_empty(self) -> None:
        result = diff_against_curated([], {"a", "b"})
        assert result == []

    def test_preserves_active_order(self) -> None:
        active = [
            {"slug": "z", "path": "/z"},
            {"slug": "a", "path": "/a"},
            {"slug": "m", "path": "/m"},
        ]
        result = diff_against_curated(active, set())
        assert [r["slug"] for r in result] == ["z", "a", "m"]
