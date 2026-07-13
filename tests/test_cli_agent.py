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


def test_agent_add_creates_task_with_next_ext_id(fake_http):
    calls, responses = fake_http
    responses[("GET", "agents/hal/tasks/")] = (
        200, json.dumps([{"ext_id": "T3", "title": "a"}, {"ext_id": "junk", "title": "b"}]))
    r = CliRunner().invoke(main, [
        "agent", "add", "--slug", "hal", "--title", "Track the thing",
        "--next-action", "Read the doc", "--status", "In progress",
        "--owner", "Jonathan", "--assigned", "Hal",
        "--links", "Thread|https://t.example, https://bare.example"])
    assert r.exit_code == 0, r.output
    method, url, body = calls[-1]
    assert (method, url) == ("POST", "https://x.test/api/agents/hal/tasks/sync")
    task = body["tasks"][0]
    assert task["ext_id"] == "T4"                      # next free after T3; "junk" ignored
    assert task["status"] == "in_progress"             # human text normalized
    assert task["links"] == [
        {"label": "Thread", "url": "https://t.example"},
        {"label": "link", "url": "https://bare.example"},
    ]
    assert json.loads(r.output)["added"] == "T4"


def test_agent_add_explicit_ext_id_skips_board_read(fake_http):
    calls, _ = fake_http
    r = CliRunner().invoke(main, ["agent", "add", "--slug", "hal",
                                  "--title", "X", "--ext-id", "T99"])
    assert r.exit_code == 0, r.output
    assert all(m != "GET" for m, _, _ in calls)        # no list_tasks round-trip
    assert calls[-1][2]["tasks"][0]["ext_id"] == "T99"
    assert calls[-1][2]["tasks"][0]["status"] == "suggested"   # default


def test_task_status_normalization_and_links_parsing():
    from orchestrator.agent_cli import normalize_task_status, parse_task_links, next_task_ext_id
    assert normalize_task_status("Shipped") == "done"
    assert normalize_task_status("won't do") == "declined"
    assert normalize_task_status("Blocked") == "in_progress"   # waiting is assigned, not status
    assert normalize_task_status("") == "suggested"
    assert parse_task_links("") == []
    assert parse_task_links("A|u1, B|u2") == [
        {"label": "A", "url": "u1"}, {"label": "B", "url": "u2"}]
    assert next_task_ext_id([]) == "T1"
    assert next_task_ext_id([{"ext_id": "T7"}, {"ext_id": "row2"}]) == "T8"
