"""Tests for `canopy observations` and `canopy proposals` CLI commands."""
from pathlib import Path

import yaml
from click.testing import CliRunner

from orchestrator.cli import main


def _seed_obs(canopy_dir: Path, **overrides) -> dict:
    obs_dir = canopy_dir / "observations"
    obs_dir.mkdir(parents=True, exist_ok=True)
    obs = {
        "id": "aaaaaaaaaaaa",
        "type": "friction",
        "description": "Test observation description",
        "severity": "high",
        "frequency": 3,
        "sessions": ["s1"],
        "related_servers": [],
        "lifecycle_stage": None,
        "status": "pending",
        "created": "2026-04-27",
    }
    obs.update(overrides)
    (obs_dir / f"{obs['id']}.yaml").write_text(yaml.dump(obs))
    return obs


def _seed_proposal(canopy_dir: Path, **overrides) -> dict:
    p_dir = canopy_dir / "proposals"
    p_dir.mkdir(parents=True, exist_ok=True)
    p = {
        "id": "bbbbbbbbbbbb",
        "type": "new_tool",
        "action": "Add `canopy foo` to do bar.",
        "target_repo": "~/emdash-projects/canopy",
        "ownership": "self",
        "motivation": "Because reasons.",
        "observation_id": "aaaaaaaaaaaa",
        "complexity": "low",
        "verification": {"type": "replay", "confidence": "high"},
        "status": "pending",
        "failure_reason": None,
        "created": "2026-04-27",
    }
    p.update(overrides)
    (p_dir / f"{p['id']}.yaml").write_text(yaml.dump(p))
    return p


class TestObservationsList:
    def test_empty_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        result = CliRunner().invoke(main, ["observations", "list"])
        assert result.exit_code == 0
        assert "No observations" in result.output

    def test_lists_observations(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        _seed_obs(tmp_path)
        result = CliRunner().invoke(main, ["observations", "list"])
        assert result.exit_code == 0
        assert "aaaaaaaaaaaa" in result.output
        assert "[high]" in result.output
        assert "Test observation description" in result.output

    def test_filter_by_severity(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        _seed_obs(tmp_path, id="111111111111", severity="high")
        _seed_obs(tmp_path, id="222222222222", severity="low")
        result = CliRunner().invoke(main, ["observations", "list", "--severity", "high"])
        assert "111111111111" in result.output
        assert "222222222222" not in result.output

    def test_filter_by_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        _seed_obs(tmp_path, id="333333333333", status="pending")
        _seed_obs(tmp_path, id="444444444444", status="addressed")
        result = CliRunner().invoke(main, ["observations", "list", "--status", "addressed"])
        assert "444444444444" in result.output
        assert "333333333333" not in result.output

    def test_json_output(self, tmp_path, monkeypatch):
        import json
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        _seed_obs(tmp_path)
        result = CliRunner().invoke(main, ["observations", "list", "--json-output"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["id"] == "aaaaaaaaaaaa"


class TestObservationsShow:
    def test_show_full_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        _seed_obs(tmp_path)
        result = CliRunner().invoke(main, ["observations", "show", "aaaaaaaaaaaa"])
        assert result.exit_code == 0
        assert "id: aaaaaaaaaaaa" in result.output
        assert "Test observation description" in result.output

    def test_show_by_prefix(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        _seed_obs(tmp_path)
        result = CliRunner().invoke(main, ["observations", "show", "aaa"])
        assert result.exit_code == 0
        assert "id: aaaaaaaaaaaa" in result.output

    def test_show_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        result = CliRunner().invoke(main, ["observations", "show", "nope"])
        assert result.exit_code != 0
        assert "No observation found" in result.output

    def test_show_ambiguous_prefix(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        _seed_obs(tmp_path, id="abc111111111")
        _seed_obs(tmp_path, id="abc222222222")
        result = CliRunner().invoke(main, ["observations", "show", "abc"])
        assert result.exit_code != 0
        assert "Multiple matches" in result.output


class TestProposalsList:
    def test_empty_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        result = CliRunner().invoke(main, ["proposals", "list"])
        assert result.exit_code == 0
        assert "No proposals" in result.output

    def test_lists_proposals(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        _seed_proposal(tmp_path)
        result = CliRunner().invoke(main, ["proposals", "list"])
        assert result.exit_code == 0
        assert "bbbbbbbbbbbb" in result.output
        assert "Add `canopy foo`" in result.output
        assert "conf=high" in result.output

    def test_filter_by_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        _seed_proposal(tmp_path, id="555555555555", status="pending")
        _seed_proposal(tmp_path, id="666666666666", status="implemented")
        result = CliRunner().invoke(main, ["proposals", "list", "--status", "implemented"])
        assert "666666666666" in result.output
        assert "555555555555" not in result.output

    def test_filter_by_complexity(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        _seed_proposal(tmp_path, id="777777777777", complexity="low")
        _seed_proposal(tmp_path, id="888888888888", complexity="high")
        result = CliRunner().invoke(main, ["proposals", "list", "--complexity", "low"])
        assert "777777777777" in result.output
        assert "888888888888" not in result.output


class TestProposalsShow:
    def test_show_full_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        _seed_proposal(tmp_path)
        result = CliRunner().invoke(main, ["proposals", "show", "bbb"])
        assert result.exit_code == 0
        assert "id: bbbbbbbbbbbb" in result.output
        assert "target_repo:" in result.output

    def test_show_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("orchestrator.cli.ensure_canopy_dir", lambda: tmp_path)
        result = CliRunner().invoke(main, ["proposals", "show", "nope"])
        assert result.exit_code != 0
        assert "No proposal found" in result.output
