"""Tests for the resolve_pm_dir.sh path resolver."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "canopy"
    / "skills"
    / "product-management"
    / "scripts"
    / "resolve_pm_dir.sh"
)


def _run(cwd: Path, home: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "HOME": str(home),
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=str(repo), check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo),
        check=True,
    )
    # initial commit so HEAD exists
    (repo / "README.md").write_text("test\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=str(repo), check=True
    )


class TestResolveInsideGitRepo:
    def test_resolves_to_repo_canopy_pm(self, tmp_path):
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        repo.mkdir()
        home.mkdir()
        _git_init(repo)

        result = _run(cwd=repo, home=home)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(repo / ".canopy" / "pm")

    def test_creates_canopy_pm_dir(self, tmp_path):
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        repo.mkdir()
        home.mkdir()
        _git_init(repo)

        _run(cwd=repo, home=home)
        assert (repo / ".canopy" / "pm").is_dir()

    def test_resolves_from_subdirectory(self, tmp_path):
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        repo.mkdir()
        home.mkdir()
        _git_init(repo)
        sub = repo / "src" / "deep"
        sub.mkdir(parents=True)

        result = _run(cwd=sub, home=home)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(repo / ".canopy" / "pm")


class TestResolveOutsideGitRepo:
    def test_falls_back_to_home_canopy_pm(self, tmp_path):
        cwd = tmp_path / "not-a-repo"
        home = tmp_path / "home"
        cwd.mkdir()
        home.mkdir()

        result = _run(cwd=cwd, home=home)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(
            home / ".canopy" / "pm" / "not-a-repo"
        )

    def test_creates_home_fallback_dir(self, tmp_path):
        cwd = tmp_path / "not-a-repo"
        home = tmp_path / "home"
        cwd.mkdir()
        home.mkdir()

        _run(cwd=cwd, home=home)
        assert (home / ".canopy" / "pm" / "not-a-repo").is_dir()
