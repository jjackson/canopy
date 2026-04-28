"""Tests for `canopy version verify` and `canopy version bump` CLI."""
import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from orchestrator.cli import main


def _setup_repo(root: Path, version: str, plugin_version: str | None = None) -> None:
    (root / "VERSION").write_text(f"{version}\n")
    plugin_dir = root / "plugins" / "canopy" / ".claude-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": "canopy", "version": plugin_version or version}) + "\n"
    )


class TestVersionVerify:
    def test_match_exits_zero(self, tmp_path):
        _setup_repo(tmp_path, "0.2.45")
        result = CliRunner().invoke(main, ["version", "verify", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_mismatch_exits_nonzero(self, tmp_path):
        _setup_repo(tmp_path, "0.2.45", plugin_version="0.2.44")
        result = CliRunner().invoke(main, ["version", "verify", "--repo", str(tmp_path)])
        assert result.exit_code != 0


class TestVersionBump:
    def test_bumps_patch(self, tmp_path):
        _setup_repo(tmp_path, "0.2.45")
        with patch("orchestrator.version_bump.fetch_origin_main_version", return_value=None):
            result = CliRunner().invoke(main, ["version", "bump", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "v0.2.46" in result.output
        assert (tmp_path / "VERSION").read_text().strip() == "0.2.46"

    def test_uses_origin_when_higher(self, tmp_path):
        _setup_repo(tmp_path, "0.2.45")
        with patch("orchestrator.version_bump.fetch_origin_main_version", return_value="0.2.50"):
            result = CliRunner().invoke(main, ["version", "bump", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "v0.2.51" in result.output
        assert (tmp_path / "VERSION").read_text().strip() == "0.2.51"

    def test_refuses_on_mismatch(self, tmp_path):
        _setup_repo(tmp_path, "0.2.45", plugin_version="0.2.44")
        result = CliRunner().invoke(main, ["version", "bump", "--repo", str(tmp_path)])
        assert result.exit_code != 0
        assert "disagree" in result.output.lower() or "mismatch" in result.output.lower()
