"""Tests for `verify_bump_when_plugin_changed` — the plugin-bump CI guard.

Builds a real local git repo per test (a `_main` ref + a feature branch
on top) and exercises the discipline-violation scenarios that motivated
the check, plus the happy paths.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from orchestrator.version_bump import verify_bump_when_plugin_changed


def _git(repo: Path, *args: str, env: dict | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo, check=True, capture_output=True, text=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
             "PATH": _env_path()} if env is None else env,
    )


def _env_path() -> str:
    import os
    return os.environ.get("PATH", "")


def _seed_repo(repo: Path, version: str = "0.1.0") -> None:
    """Create a repo with VERSION + plugin.json on a stand-in main branch."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", "main")
    (repo / "VERSION").write_text(version + "\n")
    plugin_dir = repo / "plugins" / "canopy" / ".claude-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": "canopy", "version": version}, indent=2) + "\n"
    )
    skill_dir = repo / "plugins" / "canopy" / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: alpha\n---\n# Alpha\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    # Stand-in for `origin/main` — make a local ref by that name so the
    # check can resolve it without an actual remote.
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")


def _branch(repo: Path, name: str) -> None:
    _git(repo, "checkout", "-b", name)


def _set_version(repo: Path, version: str) -> None:
    (repo / "VERSION").write_text(version + "\n")
    p = repo / "plugins" / "canopy" / ".claude-plugin" / "plugin.json"
    data = json.loads(p.read_text())
    data["version"] = version
    p.write_text(json.dumps(data, indent=2) + "\n")


def test_no_plugin_changes_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_repo(repo)
    _branch(repo, "feat/no-plugin")
    # Touch a non-plugin file
    (repo / "README.md").write_text("hello\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "docs only")

    result = verify_bump_when_plugin_changed(repo, base_ref="origin/main")
    assert result["ok"] is True
    assert result["plugin_files_changed"] == []
    assert "No plugins/canopy/" in result["reason"]


def test_plugin_changed_with_bump_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_repo(repo)
    _branch(repo, "feat/with-bump")
    skill = repo / "plugins" / "canopy" / "skills" / "alpha" / "SKILL.md"
    skill.write_text("---\nname: alpha\n---\n# Alpha v2\n")
    _set_version(repo, "0.1.1")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "feat(alpha): bump to 0.1.1")

    result = verify_bump_when_plugin_changed(repo, base_ref="origin/main")
    assert result["ok"] is True, result["reason"]
    assert result["local_version"] == "0.1.1"
    assert result["main_version"] == "0.1.0"
    assert any("alpha/SKILL.md" in p for p in result["plugin_files_changed"])


def test_plugin_changed_without_bump_fails(tmp_path: Path) -> None:
    """The discipline failure CLAUDE.md calls out as the #1 mistake."""
    repo = tmp_path / "repo"
    _seed_repo(repo)
    _branch(repo, "feat/forgot-bump")
    skill = repo / "plugins" / "canopy" / "skills" / "alpha" / "SKILL.md"
    skill.write_text("---\nname: alpha\n---\n# Alpha v2\n")
    # Note: NO version bump
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "feat(alpha): silent change")

    result = verify_bump_when_plugin_changed(repo, base_ref="origin/main")
    assert result["ok"] is False
    assert result["local_version"] == "0.1.0"
    assert result["main_version"] == "0.1.0"
    assert "VERSION" in result["reason"] and "did not advance" in result["reason"]


def test_version_and_plugin_json_disagree_fails(tmp_path: Path) -> None:
    """Branch bumped VERSION but forgot plugin.json (or vice versa)."""
    repo = tmp_path / "repo"
    _seed_repo(repo)
    _branch(repo, "feat/half-bump")
    skill = repo / "plugins" / "canopy" / "skills" / "alpha" / "SKILL.md"
    skill.write_text("---\nname: alpha\n---\n# Alpha v2\n")
    (repo / "VERSION").write_text("0.1.1\n")  # only one of two bumped
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "feat(alpha): half bump")

    result = verify_bump_when_plugin_changed(repo, base_ref="origin/main")
    assert result["ok"] is False
    assert "disagree" in result["reason"]


def test_unreachable_base_ref_skips(tmp_path: Path) -> None:
    """When origin/main isn't fetched, the check is skipped (not a hard fail)."""
    repo = tmp_path / "repo"
    _seed_repo(repo)
    # Delete the stand-in ref to simulate "no remote / not fetched".
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    _branch(repo, "feat/no-base")
    (repo / "plugins" / "canopy" / "skills" / "alpha" / "SKILL.md").write_text("changed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "change without base")

    result = verify_bump_when_plugin_changed(repo, base_ref="origin/main")
    assert result["skipped"] is True
    assert result["ok"] is True
    assert "not reachable" in result["reason"]


def test_branch_with_only_main_at_old_version(tmp_path: Path) -> None:
    """If branch matches main exactly, no diff and no failure."""
    repo = tmp_path / "repo"
    _seed_repo(repo)
    _branch(repo, "feat/empty")
    # No commits beyond main
    result = verify_bump_when_plugin_changed(repo, base_ref="origin/main")
    assert result["ok"] is True
    assert result["plugin_files_changed"] == []
