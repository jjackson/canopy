# tests/test_cli_agent.py
import json
import pytest
from click.testing import CliRunner
from orchestrator.cli import main


@pytest.fixture
def fake_http(monkeypatch):
    calls = []
    responses = {}

    def transport(method, url, headers, body):
        calls.append((method, url, json.loads(body) if body else None))
        return responses.get((method, url.split("/api/")[1]), (200, "{}"))

    monkeypatch.setenv("CANOPY_WEB_PAT", "t")
    monkeypatch.setenv("CANOPY_WEB_API_URL", "https://x.test")
    monkeypatch.setattr("orchestrator.canopy_web.urllib_transport", transport)
    return calls, responses


def test_agent_register(fake_http):
    calls, _ = fake_http
    r = CliRunner().invoke(main, ["agent", "register", "--slug", "echo", "--name", "Echo",
                                  "--email", "echo@dimagi-ai.com", "--persona", "p"])
    assert r.exit_code == 0, r.output
    assert calls[0][:2] == ("POST", "https://x.test/api/agents/")
    assert calls[0][2]["slug"] == "echo"


def test_agent_commands_lists(fake_http):
    calls, responses = fake_http
    responses[("GET", "agents/echo/commands?status=pending")] = (
        200, json.dumps([{"id": 7, "kind": "dispatch", "task_title": "Do", "created_by": "jj", "payload": None}]))
    r = CliRunner().invoke(main, ["agent", "commands", "--slug", "echo"])
    assert r.exit_code == 0, r.output
    assert "#7" in r.output and "dispatch" in r.output


def test_agent_tasks_lists(fake_http):
    calls, responses = fake_http
    responses[("GET", "agents/echo/tasks/")] = (
        200, json.dumps([{"ext_id": "T1", "title": "a"}, {"ext_id": "T2", "title": "b"}]))
    r = CliRunner().invoke(main, ["agent", "tasks", "--slug", "echo"])
    assert r.exit_code == 0, r.output
    assert calls[0][:2] == ("GET", "https://x.test/api/agents/echo/tasks/")
    assert "T1" in r.output and "T2" in r.output


def test_agent_apply(fake_http):
    calls, _ = fake_http
    r = CliRunner().invoke(main, ["agent", "apply", "--slug", "echo", "--id", "7", "--note", "ok"])
    assert r.exit_code == 0, r.output
    assert calls[0] == ("POST", "https://x.test/api/agents/echo/commands/7/apply", {"result_note": "ok"})


def test_agent_error_exits_nonzero(fake_http):
    calls, responses = fake_http
    responses[("POST", "agents/echo/commands/7/apply")] = (404, "missing")
    r = CliRunner().invoke(main, ["agent", "apply", "--slug", "echo", "--id", "7"])
    assert r.exit_code != 0
    assert "404" in r.output
