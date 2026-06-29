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
