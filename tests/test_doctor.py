"""Tests for the doctor health-check module and the `canopy doctor` CLI."""
import json
from pathlib import Path

from click.testing import CliRunner

from orchestrator import doctor
from orchestrator.cli import main


def _make_healthy_home(home: Path, canopy_dir: Path) -> None:
    """Populate a tmp home + canopy dir so every check passes."""
    claude = home / ".claude"
    (claude / "plugins").mkdir(parents=True)
    canopy_dir.mkdir(parents=True, exist_ok=True)

    # Hook registration
    (claude / "settings.json").write_text(json.dumps({
        "hooks": {
            "PostToolUse": [
                {"hooks": [{"command": "python3 /path/to/hooks/post_tool_use.py"}]}
            ]
        }
    }))
    # Session log
    (canopy_dir / "session-log.jsonl").write_text('{"a": 1}\n{"b": 2}\n')
    # Repo map
    (canopy_dir / "repo-map.json").write_text(json.dumps({"proj": "owner/repo"}))
    # Workbench token (mode 600, non-empty)
    token = canopy_dir / "workbench-token"
    token.write_text("a-secret-token-value")
    token.chmod(0o600)
    # Installed plugins
    (claude / "plugins" / "installed_plugins.json").write_text(json.dumps({
        "plugins": {"canopy@canopy": [{"version": "0.2.119"}]}
    }))


class TestCheckHookRegistered:
    def test_missing_settings_fails(self, tmp_path):
        r = doctor.check_hook_registered(home=tmp_path)
        assert r.ok is False
        assert "not found" in r.detail

    def test_registered_passes(self, tmp_path):
        claude = tmp_path / ".claude"
        claude.mkdir(parents=True)
        (claude / "settings.json").write_text(json.dumps({
            "hooks": {"PostToolUse": [{"hooks": [{"command": "x post_tool_use.py"}]}]}
        }))
        r = doctor.check_hook_registered(home=tmp_path)
        assert r.ok is True

    def test_present_but_unregistered_fails(self, tmp_path):
        claude = tmp_path / ".claude"
        claude.mkdir(parents=True)
        (claude / "settings.json").write_text(json.dumps({"hooks": {}}))
        r = doctor.check_hook_registered(home=tmp_path)
        assert r.ok is False

    def test_malformed_json_fails_gracefully(self, tmp_path):
        claude = tmp_path / ".claude"
        claude.mkdir(parents=True)
        (claude / "settings.json").write_text("{not json")
        r = doctor.check_hook_registered(home=tmp_path)
        assert r.ok is False


class TestCheckSessionLog:
    def test_missing_fails(self, tmp_path):
        r = doctor.check_session_log(canopy_dir=tmp_path)
        assert r.ok is False

    def test_empty_fails(self, tmp_path):
        (tmp_path / "session-log.jsonl").write_text("\n  \n")
        r = doctor.check_session_log(canopy_dir=tmp_path)
        assert r.ok is False

    def test_populated_passes(self, tmp_path):
        (tmp_path / "session-log.jsonl").write_text('{"a":1}\n{"b":2}\n')
        r = doctor.check_session_log(canopy_dir=tmp_path)
        assert r.ok is True
        assert "2 entries" in r.detail


class TestCheckRepoMap:
    def test_missing_fails(self, tmp_path):
        r = doctor.check_repo_map(canopy_dir=tmp_path)
        assert r.ok is False

    def test_valid_passes(self, tmp_path):
        (tmp_path / "repo-map.json").write_text(json.dumps({"a": "b", "c": "d"}))
        r = doctor.check_repo_map(canopy_dir=tmp_path)
        assert r.ok is True
        assert "2 project mappings" in r.detail

    def test_malformed_fails(self, tmp_path):
        (tmp_path / "repo-map.json").write_text("[not, valid")
        r = doctor.check_repo_map(canopy_dir=tmp_path)
        assert r.ok is False


class TestCheckWorkbenchToken:
    def test_missing_fails(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        r = doctor.check_workbench_token(home=tmp_path, canopy_dir=tmp_path)
        assert r.ok is False

    def test_empty_fails(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        token = tmp_path / "workbench-token"
        token.write_text("   ")
        token.chmod(0o600)
        r = doctor.check_workbench_token(home=tmp_path, canopy_dir=tmp_path)
        assert r.ok is False
        assert "empty" in r.detail

    def test_wrong_perms_fails(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        token = tmp_path / "workbench-token"
        token.write_text("secret")
        token.chmod(0o644)
        r = doctor.check_workbench_token(home=tmp_path, canopy_dir=tmp_path)
        assert r.ok is False
        assert "600" in r.detail

    def test_valid_passes(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        token = tmp_path / "workbench-token"
        token.write_text("secret")
        token.chmod(0o600)
        r = doctor.check_workbench_token(home=tmp_path, canopy_dir=tmp_path)
        assert r.ok is True

    def test_plugin_data_env_takes_precedence(self, tmp_path, monkeypatch):
        plugin_data = tmp_path / "plugin_data"
        plugin_data.mkdir()
        token = plugin_data / "workbench-token"
        token.write_text("env-token")
        token.chmod(0o600)
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(plugin_data))
        canopy_dir = tmp_path / "canopy"
        canopy_dir.mkdir()
        r = doctor.check_workbench_token(home=tmp_path, canopy_dir=canopy_dir)
        assert r.ok is True


class TestCheckPluginVersion:
    def test_missing_fails(self, tmp_path):
        r = doctor.check_plugin_version(home=tmp_path)
        assert r.ok is False

    def test_valid_passes(self, tmp_path):
        plugins = tmp_path / ".claude" / "plugins"
        plugins.mkdir(parents=True)
        (plugins / "installed_plugins.json").write_text(json.dumps({
            "plugins": {"canopy@canopy": [{"version": "0.2.119"}]}
        }))
        r = doctor.check_plugin_version(home=tmp_path)
        assert r.ok is True
        assert "0.2.119" in r.detail


class TestRunDoctor:
    def test_all_pass(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        home = tmp_path / "home"
        canopy_dir = home / ".claude" / "canopy"
        home.mkdir()
        _make_healthy_home(home, canopy_dir)
        results, overall_ok = doctor.run_doctor(home=home, canopy_dir=canopy_dir)
        assert overall_ok is True
        assert all(r.ok for r in results)
        assert len(results) == 5

    def test_one_failure_flips_overall(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        home = tmp_path / "home"
        canopy_dir = home / ".claude" / "canopy"
        home.mkdir()
        _make_healthy_home(home, canopy_dir)
        # Break one check.
        (canopy_dir / "repo-map.json").unlink()
        results, overall_ok = doctor.run_doctor(home=home, canopy_dir=canopy_dir)
        assert overall_ok is False
        assert any(not r.ok for r in results)


class TestDoctorCLI:
    def test_all_pass_exit_zero(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        home = tmp_path / "home"
        canopy_dir = home / ".claude" / "canopy"
        home.mkdir()
        _make_healthy_home(home, canopy_dir)
        monkeypatch.setattr(doctor.Path, "home", staticmethod(lambda: home))
        monkeypatch.setattr(doctor, "CANOPY_DIR", canopy_dir)

        result = CliRunner().invoke(main, ["doctor"])
        assert result.exit_code == 0
        assert "All checks passed" in result.output

    def test_failure_exit_nonzero(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        home = tmp_path / "home"
        canopy_dir = home / ".claude" / "canopy"
        home.mkdir()
        _make_healthy_home(home, canopy_dir)
        (canopy_dir / "session-log.jsonl").unlink()
        monkeypatch.setattr(doctor.Path, "home", staticmethod(lambda: home))
        monkeypatch.setattr(doctor, "CANOPY_DIR", canopy_dir)

        result = CliRunner().invoke(main, ["doctor"])
        assert result.exit_code != 0
        assert "FAIL" in result.output

    def test_json_output_is_valid(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        home = tmp_path / "home"
        canopy_dir = home / ".claude" / "canopy"
        home.mkdir()
        _make_healthy_home(home, canopy_dir)
        monkeypatch.setattr(doctor.Path, "home", staticmethod(lambda: home))
        monkeypatch.setattr(doctor, "CANOPY_DIR", canopy_dir)

        result = CliRunner().invoke(main, ["doctor", "--json-output"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert len(payload["checks"]) == 5
        assert all("name" in c and "ok" in c and "detail" in c for c in payload["checks"])
