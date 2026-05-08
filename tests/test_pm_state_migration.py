"""Tests for the legacy-state migration baked into resolve_pm_dir.sh."""
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


def _git_init_with_origin(repo: Path, origin_url: str) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=str(repo), check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo),
        check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", origin_url],
        cwd=str(repo),
        check=True,
    )
    (repo / "README.md").write_text("test\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=str(repo), check=True
    )


def _seed_legacy_state(home: Path, project: str) -> Path:
    legacy = home / ".canopy" / "pm" / project
    legacy.mkdir(parents=True)
    (legacy / "context.md").write_text("# context\nlegacy content\n")
    (legacy / "learnings.md").write_text("# learnings\nlegacy items\n")
    (legacy / "autonomous.yaml").write_text("email:\n  to: x@y.com\n")
    runs = legacy / "runs"
    runs.mkdir()
    (runs / "2026-01-01-user-value.md").write_text("# run\n")
    return legacy


class TestMigrationFromLegacyOriginUrl:
    def test_copies_all_files(self, tmp_path):
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        repo.mkdir()
        home.mkdir()
        _git_init_with_origin(repo, "https://github.com/u/foo-proj.git")
        _seed_legacy_state(home, "foo-proj")

        result = _run(cwd=repo, home=home)
        assert result.returncode == 0, result.stderr

        new = repo / ".canopy" / "pm"
        assert (new / "context.md").read_text() == "# context\nlegacy content\n"
        assert (new / "learnings.md").read_text() == "# learnings\nlegacy items\n"
        assert (new / "autonomous.yaml").read_text() == "email:\n  to: x@y.com\n"
        assert (new / "runs" / "2026-01-01-user-value.md").is_file()

    def test_creates_migrated_marker(self, tmp_path):
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        repo.mkdir()
        home.mkdir()
        _git_init_with_origin(repo, "https://github.com/u/foo-proj.git")
        _seed_legacy_state(home, "foo-proj")

        _run(cwd=repo, home=home)

        marker = home / ".canopy" / "pm" / "foo-proj" / ".migrated"
        assert marker.is_file()
        body = marker.read_text()
        assert "migrated_to:" in body
        assert str(repo / ".canopy" / "pm") in body
        assert "timestamp:" in body

    def test_creates_migration_commit(self, tmp_path):
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        repo.mkdir()
        home.mkdir()
        _git_init_with_origin(repo, "https://github.com/u/foo-proj.git")
        _seed_legacy_state(home, "foo-proj")

        _run(cwd=repo, home=home)

        log = subprocess.run(
            ["git", "log", "--pretty=format:%s", "-n", "2"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        assert log[0].startswith("chore(canopy-pm): migrate state from")
        assert "foo-proj" in log[0]

    def test_migration_is_idempotent(self, tmp_path):
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        repo.mkdir()
        home.mkdir()
        _git_init_with_origin(repo, "https://github.com/u/foo-proj.git")
        _seed_legacy_state(home, "foo-proj")

        _run(cwd=repo, home=home)
        _run(cwd=repo, home=home)

        log = subprocess.run(
            ["git", "log", "--pretty=format:%s"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        migration_commits = [
            line for line in log if line.startswith("chore(canopy-pm): migrate")
        ]
        assert len(migration_commits) == 1


class TestMigrationSkippedWhenDestNonEmpty:
    def test_skips_when_dest_has_content(self, tmp_path):
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        repo.mkdir()
        home.mkdir()
        _git_init_with_origin(repo, "https://github.com/u/foo-proj.git")
        _seed_legacy_state(home, "foo-proj")
        (repo / ".canopy" / "pm").mkdir(parents=True)
        (repo / ".canopy" / "pm" / "context.md").write_text("# pre-existing\n")

        _run(cwd=repo, home=home)

        # dest content must be untouched
        assert (
            (repo / ".canopy" / "pm" / "context.md").read_text()
            == "# pre-existing\n"
        )
        # marker NOT created since migration skipped
        marker = home / ".canopy" / "pm" / "foo-proj" / ".migrated"
        assert not marker.exists()


class TestMigrationSkippedWhenMarkerPresent:
    def test_skips_when_marker_exists(self, tmp_path):
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        repo.mkdir()
        home.mkdir()
        _git_init_with_origin(repo, "https://github.com/u/foo-proj.git")
        legacy = _seed_legacy_state(home, "foo-proj")
        (legacy / ".migrated").write_text("migrated_to: somewhere\n")

        _run(cwd=repo, home=home)

        # Dest dir created but no copies happened
        assert (repo / ".canopy" / "pm").is_dir()
        assert not (repo / ".canopy" / "pm" / "context.md").exists()


class TestMigrationFallbackProjectName:
    def test_uses_git_common_dir_basename_when_no_origin(self, tmp_path):
        # Repo has NO origin remote; fall back to dirname of git-common-dir.
        # In a non-worktree setup this is the parent of `.git`, i.e. the repo's
        # own basename.
        repo = tmp_path / "fallback-proj"
        home = tmp_path / "home"
        repo.mkdir()
        home.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=str(repo), check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=str(repo),
            check=True,
        )
        (repo / "README.md").write_text("test\n")
        subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "init"], cwd=str(repo), check=True
        )
        _seed_legacy_state(home, "fallback-proj")

        result = _run(cwd=repo, home=home)
        assert result.returncode == 0, result.stderr

        new = repo / ".canopy" / "pm"
        assert (new / "context.md").is_file()
        assert (home / ".canopy" / "pm" / "fallback-proj" / ".migrated").is_file()


class TestNoMigrationOutsideGitRepo:
    def test_no_migration_attempted_outside_repo(self, tmp_path):
        cwd = tmp_path / "loose"
        home = tmp_path / "home"
        cwd.mkdir()
        home.mkdir()
        _seed_legacy_state(home, "loose")

        result = _run(cwd=cwd, home=home)
        assert result.returncode == 0, result.stderr
        # Resolver returns home-dir fallback, NOT migrated content
        assert result.stdout.strip() == str(home / ".canopy" / "pm" / "loose")
        # Legacy dir untouched (no marker created)
        assert not (home / ".canopy" / "pm" / "loose" / ".migrated").exists()
