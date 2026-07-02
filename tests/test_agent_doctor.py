"""Tests for the per-agent doctor (`canopy agent doctor`)."""
import json
from types import SimpleNamespace

from click.testing import CliRunner

from orchestrator.agent_doctor import (
    check_email_auth,
    check_gating,
    check_identity,
    check_registration,
    check_secrets_manifest,
    run_agent_doctor,
)
from orchestrator.canopy_web import CanopyError
from orchestrator.cli import main


# --------------------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------------------

def _agent_repo(tmp_path, *, email="hal@dimagi-ai.com", slug="hal",
                gating=True, secrets=True):
    repo = tmp_path / slug
    (repo / ".claude-plugin").mkdir(parents=True)
    (repo / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": slug}))
    (repo / "config").mkdir()
    (repo / "config" / "agent.json").write_text(
        json.dumps({"name": slug.title(), "email": email}))
    if gating:
        (repo / "config" / "gating.json").write_text(
            json.dumps({"deny": [{"tool": "Bash", "pattern": "x", "message": "m"}],
                        "approve": []}))
    if secrets:
        (repo / "config" / "secrets.yaml").write_text(
            "secrets:\n"
            "  - name: gog client\n"
            f"    op: op://AI-Agents/{slug} gog client/notesPlain\n"
            f"    target: \"~/Library/Application Support/gogcli/credentials-{slug}.json\"\n"
            "env:\n"
            f"  target: \"~/.{slug}/.env\"\n"
            "  vars:\n"
            f"    - key: {slug.upper()}_GMAIL_ACCOUNT\n"
            f"      value: \"{email}\"\n")
    return repo


def _gog_home(tmp_path, *, slug="hal", account="hal@dimagi-ai.com"):
    home = tmp_path / "gogcli"
    home.mkdir()
    (home / f"credentials-{slug}.json").write_text('{"client_id": "x"}')
    (home / "config.json").write_text(
        json.dumps({"account_clients": {account: slug}}))
    return str(home)


def _ok_runner(cmd, capture_output, text, timeout):
    return SimpleNamespace(returncode=0, stdout="", stderr="")


class _FakeClient:
    def __init__(self, identity, *, error=None, pending=()):
        self._error, self._pending = error, list(pending)

    def pending_commands(self):
        if self._error:
            raise self._error
        return self._pending


def _client_factory(*, error=None, pending=()):
    return lambda identity: _FakeClient(identity, error=error, pending=pending)


# --------------------------------------------------------------------------------------
# individual checks
# --------------------------------------------------------------------------------------

def test_identity_ok_reports_slug_mailbox_client(tmp_path):
    result, ident = check_identity(_agent_repo(tmp_path))
    assert result.ok
    assert ident.account == "hal@dimagi-ai.com"
    assert "gog_client=hal" in result.detail


def test_identity_missing_mailbox_fails(tmp_path):
    result, ident = check_identity(_agent_repo(tmp_path, email=""))
    assert not result.ok
    assert ident is None


def test_gating_missing_file_fails(tmp_path):
    result = check_gating(_agent_repo(tmp_path, gating=False))
    assert not result.ok
    assert "no rails" in result.detail


def test_gating_counts_rules(tmp_path):
    result = check_gating(_agent_repo(tmp_path))
    assert result.ok
    assert "1 deny rail(s)" in result.detail


def test_secrets_manifest_missing_points_at_provision(tmp_path):
    result = check_secrets_manifest(_agent_repo(tmp_path, secrets=False))
    assert not result.ok
    assert "canopy provision" in result.detail


def test_secrets_manifest_counts_entries(tmp_path):
    result = check_secrets_manifest(_agent_repo(tmp_path))
    assert result.ok
    assert "1 file secret(s), 1 env var(s)" in result.detail


def test_email_auth_skipped_without_identity():
    result = check_email_auth(None)
    assert not result.ok
    assert "skipped" in result.detail


def test_registration_404_names_register_command(tmp_path):
    _, ident = check_identity(_agent_repo(tmp_path))
    result = check_registration(
        ident, client_factory=_client_factory(
            error=CanopyError("GET /api/agents/hal/commands -> 404: agent 'hal' not found")))
    assert not result.ok
    assert "agent-publish register" in result.detail


def test_registration_ok_counts_pending(tmp_path):
    _, ident = check_identity(_agent_repo(tmp_path))
    result = check_registration(
        ident, client_factory=_client_factory(pending=[object(), object()]))
    assert result.ok
    assert "2 pending" in result.detail


# --------------------------------------------------------------------------------------
# composition + CLI
# --------------------------------------------------------------------------------------

def test_run_agent_doctor_all_green(tmp_path):
    repo = _agent_repo(tmp_path)
    results, ok = run_agent_doctor(
        repo, gog_dir=_gog_home(tmp_path), runner=_ok_runner,
        client_factory=_client_factory())
    assert ok
    assert [r.ok for r in results] == [True] * 5


def test_run_agent_doctor_identity_failure_degrades_dependents(tmp_path):
    repo = _agent_repo(tmp_path, email="")
    results, ok = run_agent_doctor(
        repo, gog_dir=_gog_home(tmp_path), runner=_ok_runner,
        client_factory=_client_factory())
    assert not ok
    by_name = {r.name: r for r in results}
    assert not by_name["Identity"].ok
    assert "skipped" in by_name["Email auth (gog)"].detail
    assert "skipped" in by_name["canopy-web board"].detail
    # non-identity checks still ran
    assert by_name["Gating rails"].ok
    assert by_name["Secrets manifest"].ok


def test_cli_agent_doctor_json_and_exit_code(tmp_path, monkeypatch):
    repo = _agent_repo(tmp_path, secrets=False)
    monkeypatch.setattr(
        "orchestrator.agent_doctor.preflight",
        lambda identity, gog_dir=None, runner=None: (True, ["OK: gog Gmail ready"]))
    monkeypatch.setattr(
        "orchestrator.agent_doctor.AgentClient", _client_factory())
    result = CliRunner().invoke(main, ["agent", "doctor", "--repo", str(repo), "--json-output"])
    assert result.exit_code == 1  # secrets manifest missing
    payload = json.loads(result.output)
    assert payload["ok"] is False
    names = [c["name"] for c in payload["checks"]]
    assert names == ["Identity", "Gating rails", "Secrets manifest",
                     "Email auth (gog)", "canopy-web board"]
