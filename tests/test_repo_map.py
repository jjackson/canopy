from pathlib import Path
import pytest
from orchestrator.repo_map import (
    load_repo_map,
    save_repo_mapping,
    get_repo_for_project,
    extract_repo_from_git_url,
)


class TestExtractRepoFromGitUrl:
    def test_ssh_url(self):
        assert extract_repo_from_git_url("git@github.com:jjackson/connect-labs.git") == "jjackson/connect-labs"

    def test_https_url(self):
        assert extract_repo_from_git_url("https://github.com/jjackson/connect-labs.git") == "jjackson/connect-labs"

    def test_https_no_dot_git(self):
        assert extract_repo_from_git_url("https://github.com/jjackson/connect-labs") == "jjackson/connect-labs"

    def test_invalid_url_returns_none(self):
        assert extract_repo_from_git_url("not-a-url") is None

    def test_empty_returns_none(self):
        assert extract_repo_from_git_url("") is None


class TestLoadRepoMap:
    def test_missing_file_returns_empty(self, tmp_path):
        assert load_repo_map(tmp_path / "repo-map.json") == {}

    def test_returns_dict(self, tmp_path):
        assert isinstance(load_repo_map(tmp_path / "repo-map.json"), dict)


class TestSaveAndGet:
    def test_save_creates_file(self, tmp_path):
        path = tmp_path / "repo-map.json"
        save_repo_mapping(path, "-Users-jjackson-project", "jjackson/my-repo")
        assert path.exists()

    def test_round_trip(self, tmp_path):
        path = tmp_path / "repo-map.json"
        save_repo_mapping(path, "-Users-jjackson-project", "jjackson/my-repo")
        repo_map = load_repo_map(path)
        assert get_repo_for_project(repo_map, "-Users-jjackson-project") == "jjackson/my-repo"

    def test_unknown_project_returns_none(self, tmp_path):
        path = tmp_path / "repo-map.json"
        repo_map = load_repo_map(path)
        assert get_repo_for_project(repo_map, "unknown") is None

    def test_multiple_mappings(self, tmp_path):
        path = tmp_path / "repo-map.json"
        save_repo_mapping(path, "proj-a", "owner/repo-a")
        save_repo_mapping(path, "proj-b", "owner/repo-b")
        repo_map = load_repo_map(path)
        assert get_repo_for_project(repo_map, "proj-a") == "owner/repo-a"
        assert get_repo_for_project(repo_map, "proj-b") == "owner/repo-b"
