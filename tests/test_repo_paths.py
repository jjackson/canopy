"""Tests for resolve_repo_path — multi-convention emdash root resolution."""
import subprocess
from pathlib import Path

import pytest

from orchestrator.repo_paths import resolve_repo_path, list_known_roots


def _make_git_repo(path: Path) -> None:
    """Create a real git repo (with .git directory) at `path`."""
    path.mkdir(parents=True)
    subprocess.check_call(["git", "init", "-q", "-b", "main"], cwd=path)


class TestResolveRepoPathByShortName:
    def test_finds_repo_in_first_root(self, tmp_path):
        roots = (str(tmp_path / "first"), str(tmp_path / "second"))
        _make_git_repo(tmp_path / "first" / "ace")
        result = resolve_repo_path("ace", roots=roots)
        assert result == tmp_path / "first" / "ace"

    def test_finds_repo_in_second_root_when_first_missing(self, tmp_path):
        roots = (str(tmp_path / "missing"), str(tmp_path / "second"))
        _make_git_repo(tmp_path / "second" / "ace")
        result = resolve_repo_path("ace", roots=roots)
        assert result == tmp_path / "second" / "ace"

    def test_first_root_wins_when_repo_in_both(self, tmp_path):
        # User has the repo in both conventions; first listed root wins.
        roots = (str(tmp_path / "first"), str(tmp_path / "second"))
        _make_git_repo(tmp_path / "first" / "ace")
        _make_git_repo(tmp_path / "second" / "ace")
        result = resolve_repo_path("ace", roots=roots)
        assert result == tmp_path / "first" / "ace"

    def test_returns_none_when_no_match(self, tmp_path):
        roots = (str(tmp_path / "first"),)
        result = resolve_repo_path("totally-missing", roots=roots)
        assert result is None

    def test_skips_dirs_without_git(self, tmp_path):
        # A directory exists with the right name but isn't a git repo.
        (tmp_path / "first" / "ace").mkdir(parents=True)
        roots = (str(tmp_path / "first"),)
        result = resolve_repo_path("ace", roots=roots)
        assert result is None

    def test_handles_repo_names_with_hyphens(self, tmp_path):
        roots = (str(tmp_path / "r"),)
        _make_git_repo(tmp_path / "r" / "ace-web")
        result = resolve_repo_path("ace-web", roots=roots)
        assert result == tmp_path / "r" / "ace-web"


class TestResolveRepoPathByAbsolutePath:
    def test_existing_path_returned_as_is(self, tmp_path):
        repo = tmp_path / "anywhere" / "myrepo"
        _make_git_repo(repo)
        result = resolve_repo_path(str(repo))
        assert result == repo

    def test_tilde_expanded_and_used_if_exists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        _make_git_repo(tmp_path / "code" / "ace")
        # Use ~ in the input — should expand to tmp_path/code/ace.
        result = resolve_repo_path("~/code/ace")
        assert result == tmp_path / "code" / "ace"

    def test_nonexistent_path_falls_back_to_basename_search(self, tmp_path):
        # User has a hardcoded path that doesn't exist on this machine,
        # but the repo IS available under a different convention.
        # Backwards compat: extract the basename and re-resolve.
        roots = (str(tmp_path / "actual-root"),)
        _make_git_repo(tmp_path / "actual-root" / "ace")
        result = resolve_repo_path(
            "/nonexistent/path/to/ace",
            roots=roots,
        )
        assert result == tmp_path / "actual-root" / "ace"

    def test_path_exists_but_no_git_falls_back(self, tmp_path):
        # The path exists but isn't a git repo — fall back to short-name search.
        bare_dir = tmp_path / "stale" / "ace"
        bare_dir.mkdir(parents=True)
        _make_git_repo(tmp_path / "real" / "ace")
        roots = (str(tmp_path / "real"),)
        result = resolve_repo_path(str(bare_dir), roots=roots)
        assert result == tmp_path / "real" / "ace"


class TestEdgeCases:
    def test_empty_string_returns_none(self):
        assert resolve_repo_path("") is None

    def test_whitespace_only_returns_none(self):
        assert resolve_repo_path("   ") is None

    def test_none_input_returns_none(self):
        assert resolve_repo_path(None) is None  # type: ignore[arg-type]


class TestListKnownRoots:
    def test_includes_existing_roots_only(self, tmp_path):
        existing = tmp_path / "exists"
        existing.mkdir()
        roots = (str(existing), str(tmp_path / "missing"))
        result = list_known_roots(roots=roots)
        assert existing in result
        assert tmp_path / "missing" not in result

    def test_returns_paths_with_tilde_expanded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "code").mkdir()
        result = list_known_roots(roots=("~/code",))
        assert tmp_path / "code" in result
