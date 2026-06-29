# tests/test_agent_client.py
import json
from orchestrator.agent_client import AgentClient, AgentIdentity


def make_client(recorder):
    def transport(method, url, headers, body):
        recorder.append((method, url, json.loads(body) if body else None))
        return 200, "{}"
    return AgentClient({"slug": "echo", "name": "Echo", "email": "echo@dimagi-ai.com"},
                       base_url="https://x.test", token="t", transport=transport)


def test_identity_from_dict_or_model():
    c = AgentClient(AgentIdentity(slug="a"), base_url="https://x.test", token="t")
    assert c.slug == "a"
    c2 = AgentClient({"slug": "b"}, base_url="https://x.test", token="t")
    assert c2.slug == "b"


def test_register_posts_identity():
    rec = []
    c = make_client(rec)
    c.register()
    method, url, body = rec[0]
    assert method == "POST"
    assert url == "https://x.test/api/agents/"
    assert body["slug"] == "echo"
    assert body["email"] == "echo@dimagi-ai.com"


import json as _json
from orchestrator.agent_client import BoardCommand


def _recorder_client(responses):
    """responses: list of (status, text) returned in order."""
    calls = []
    seq = list(responses)
    def transport(method, url, headers, body):
        calls.append((method, url, _json.loads(body) if body else None))
        return seq.pop(0)
    c = AgentClient({"slug": "echo"}, base_url="https://x.test", token="t", transport=transport)
    return c, calls


def test_post_sync_and_skills_and_workproducts():
    c, calls = _recorder_client([(200, "{}"), (200, "{}"), (200, "{}")])
    c.post_sync(period_start="2026-06-01", period_end="2026-06-07", title="W",
                doc_url="https://doc", self_grades={"work": "C+"})
    c.put_work_products([{"title": "T", "url": "https://wp"}])
    c.put_skills([{"name": "s", "url": "https://s"}])
    assert calls[0][:2] == ("POST", "https://x.test/api/agents/echo/syncs/")
    assert calls[0][2]["self_grades"] == {"work": "C+"}
    assert calls[1][:2] == ("POST", "https://x.test/api/agents/echo/work-products/")
    assert calls[1][2] == {"work_products": [{"title": "T", "url": "https://wp"}]}
    assert calls[2][:2] == ("PUT", "https://x.test/api/agents/echo/skills/")
    assert calls[2][2] == {"skills": [{"name": "s", "url": "https://s"}]}


def test_pending_commands_parses_models():
    raw = _json.dumps([{"id": 5, "kind": "dispatch", "task_title": "Do it",
                        "created_by": "jj@dimagi.com", "payload": {"note": "go"}}])
    c, calls = _recorder_client([(200, raw)])
    cmds = c.pending_commands()
    assert calls[0][:2] == ("GET", "https://x.test/api/agents/echo/commands?status=pending")
    assert isinstance(cmds[0], BoardCommand)
    assert (cmds[0].id, cmds[0].kind, cmds[0].task_title) == (5, "dispatch", "Do it")


def test_apply_command_and_patch_task_drops_none():
    c, calls = _recorder_client([(200, "{}"), (200, "{}")])
    c.apply_command(5, result_note="done")
    c.patch_task(9, rationale="why", plan=None, status="in_progress")
    assert calls[0] == ("POST", "https://x.test/api/agents/echo/commands/5/apply", {"result_note": "done"})
    assert calls[1] == ("PATCH", "https://x.test/api/agents/echo/tasks/9/", {"rationale": "why", "status": "in_progress"})


def test_sync_tasks_wraps_payload():
    c, calls = _recorder_client([(200, "{}")])
    c.sync_tasks([{"ext_id": "T1", "title": "x"}])
    assert calls[0][:2] == ("POST", "https://x.test/api/agents/echo/tasks/sync")
    assert calls[0][2] == {"tasks": [{"ext_id": "T1", "title": "x"}]}
