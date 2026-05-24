"""Tests for orchestrator.version_bump."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.version_bump import (
    _parse,
    _format,
    bump,
    compute_next_version,
    find_version_files,
    verify,
)


def _setup_repo(tmp_path: Path, version: str, plugin_version: str | None = None) -> Path:
    """Create a minimal repo layout with VERSION and plugin.json."""
    (tmp_path / "VERSION").write_text(f"{version}\n")
    plugin_dir = tmp_path / "plugins" / "canopy" / ".claude-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": "canopy", "version": plugin_version or version}) + "\n"
    )
    return tmp_path


class TestParseFormat:
    def test_parse_valid(self):
        assert _parse("0.2.45") == (0, 2, 45)

    def test_parse_strips_whitespace(self):
        assert _parse("  0.2.45\n") == (0, 2, 45)

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse("not-a-version")
        with pytest.raises(ValueError):
            _parse("1.2")
        with pytest.raises(ValueError):
            _parse("1.2.3-rc1")

    def test_format_roundtrip(self):
        assert _format(_parse("3.7.42")) == "3.7.42"


class TestComputeNextVersion:
    def test_no_origin_bumps_local_patch(self):
        assert compute_next_version("0.2.45", None) == "0.2.46"

    def test_origin_higher_bumps_origin_patch(self):
        # Origin already moved ahead — bump from there, not from local
        assert compute_next_version("0.2.45", "0.2.50") == "0.2.51"

    def test_origin_lower_bumps_local_patch(self):
        assert compute_next_version("0.2.45", "0.2.40") == "0.2.46"

    def test_origin_equal_bumps_patch(self):
        assert compute_next_version("0.2.45", "0.2.45") == "0.2.46"


class TestVerify:
    def test_match(self, tmp_path):
        _setup_repo(tmp_path, "0.2.45")
        matches, v, p = verify(tmp_path)
        assert matches is True
        assert v == "0.2.45"
        assert p == "0.2.45"

    def test_mismatch(self, tmp_path):
        _setup_repo(tmp_path, "0.2.45", plugin_version="0.2.44")
        matches, v, p = verify(tmp_path)
        assert matches is False
        assert v == "0.2.45"
        assert p == "0.2.44"

    def test_missing_files_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            verify(tmp_path)


class TestBump:
    def test_bump_writes_both_files_no_origin(self, tmp_path):
        _setup_repo(tmp_path, "0.2.45")
        with patch("orchestrator.version_bump.fetch_origin_main_version", return_value=None):
            result = bump(tmp_path)
        assert result["new_version"] == "0.2.46"
        assert (tmp_path / "VERSION").read_text().strip() == "0.2.46"
        plugin_json = json.loads((tmp_path / "plugins" / "canopy" / ".claude-plugin" / "plugin.json").read_text())
        assert plugin_json["version"] == "0.2.46"

    def test_bump_uses_origin_when_higher(self, tmp_path):
        _setup_repo(tmp_path, "0.2.45")
        with patch("orchestrator.version_bump.fetch_origin_main_version", return_value="0.2.50"):
            result = bump(tmp_path)
        assert result["new_version"] == "0.2.51"
        assert result["previous_local"] == "0.2.45"
        assert result["origin_main"] == "0.2.50"

    def test_bump_refuses_on_mismatch(self, tmp_path):
        _setup_repo(tmp_path, "0.2.45", plugin_version="0.2.44")
        with pytest.raises(ValueError, match="disagree"):
            bump(tmp_path)

    def test_bump_with_unreachable_origin_still_works(self, tmp_path):
        _setup_repo(tmp_path, "0.2.45")
        with patch("orchestrator.version_bump.fetch_origin_main_version", return_value=None):
            result = bump(tmp_path)
        assert result["new_version"] == "0.2.46"
        assert result["origin_main"] is None

    def test_bump_updates_marketplace_json_when_present(self, tmp_path):
        """Regression: PR shipping a bump skipped marketplace.json — the file
        carries two `"version"` fields that drift if not updated. The bump
        CLI should now sync both to match plugin.json."""
        _setup_repo(tmp_path, "0.2.45")
        mp_dir = tmp_path / ".claude-plugin"
        mp_dir.mkdir(parents=True, exist_ok=True)
        (mp_dir / "marketplace.json").write_text(json.dumps({
            "name": "canopy",
            "metadata": {"version": "0.1.0"},
            "plugins": [{"name": "canopy", "version": "0.1.0"}],
        }) + "\n")
        with patch("orchestrator.version_bump.fetch_origin_main_version", return_value=None):
            result = bump(tmp_path)
        assert result["new_version"] == "0.2.46"
        assert result["marketplace_json_replacements"] == 2
        mp = json.loads((mp_dir / "marketplace.json").read_text())
        assert mp["metadata"]["version"] == "0.2.46"
        assert mp["plugins"][0]["version"] == "0.2.46"

    def test_bump_tolerates_missing_marketplace_json(self, tmp_path):
        """Test fixtures and minimal clones don't ship marketplace.json — the
        bump CLI must not require it."""
        _setup_repo(tmp_path, "0.2.45")
        with patch("orchestrator.version_bump.fetch_origin_main_version", return_value=None):
            result = bump(tmp_path)
        assert result["marketplace_json_path"] is None
        assert result["marketplace_json_replacements"] == 0


class TestFindVersionFiles:
    def test_finds_both(self, tmp_path):
        _setup_repo(tmp_path, "0.2.45")
        v, p = find_version_files(tmp_path)
        assert v.exists()
        assert p.exists()

    def test_missing_version_raises(self, tmp_path):
        plugin_dir = tmp_path / "plugins" / "canopy" / ".claude-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text('{"version": "0.0.0"}')
        with pytest.raises(FileNotFoundError, match="VERSION"):
            find_version_files(tmp_path)
