# tests/test_canopy_web.py
import json
import pytest
from orchestrator import canopy_web as cw


def test_resolve_base_url_precedence(monkeypatch):
    assert cw.resolve_base_url("https://x.test/") == "https://x.test"   # arg wins, trailing slash stripped
    monkeypatch.setenv("CANOPY_WEB_API_URL", "https://env.test/")
    assert cw.resolve_base_url(None) == "https://env.test"
    monkeypatch.delenv("CANOPY_WEB_API_URL", raising=False)
    assert cw.resolve_base_url(None) == cw.DEFAULT_API


def test_resolve_token_precedence(monkeypatch, tmp_path):
    monkeypatch.setattr(cw, "TOKEN_FILE", tmp_path / "missing")
    monkeypatch.delenv("CANOPY_WEB_PAT", raising=False)
    assert cw.resolve_token("raw-arg") == "raw-arg"
    monkeypatch.setenv("CANOPY_WEB_PAT", "env-tok")
    assert cw.resolve_token(None) == "env-tok"
    monkeypatch.delenv("CANOPY_WEB_PAT", raising=False)
    tf = tmp_path / "tok"
    tf.write_text("file-tok\n")
    monkeypatch.setattr(cw, "TOKEN_FILE", tf)
    assert cw.resolve_token(None) == "file-tok"


def test_resolve_token_missing_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("CANOPY_WEB_PAT", raising=False)
    monkeypatch.setattr(cw, "TOKEN_FILE", tmp_path / "missing")
    with pytest.raises(RuntimeError, match="canopy-web PAT"):
        cw.resolve_token(None)


def test_call_uses_transport_and_parses_json():
    seen = {}

    def fake(method, url, headers, body):
        seen.update(method=method, url=url, headers=headers, body=body)
        return 200, json.dumps({"ok": True})

    out = cw.call("POST", "/api/agents/", {"slug": "x"},
                  base_url="https://x.test", token="t", transport=fake)
    assert out == {"ok": True}
    assert seen["method"] == "POST"
    assert seen["url"] == "https://x.test/api/agents/"
    assert seen["headers"]["Authorization"] == "Bearer t"
    assert json.loads(seen["body"]) == {"slug": "x"}


def test_call_raises_canopy_error_on_4xx():
    def fake(method, url, headers, body):
        return 404, "nope"
    with pytest.raises(cw.CanopyError, match="404"):
        cw.call("GET", "/api/agents/x/", base_url="https://x.test", token="t", transport=fake)


def test_call_get_has_no_body():
    def fake(method, url, headers, body):
        assert body is None
        return 200, "[]"
    assert cw.call("GET", "/api/x", base_url="https://x.test", token="t", transport=fake) == []


def test_urllib_transport_builds_request(monkeypatch):
    captured = {}

    class FakeResp:
        status = 201
        def read(self): return b'{"created": 1}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req):
        captured["method"] = req.get_method()
        captured["url"] = req.full_url
        captured["body"] = req.data
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    status, text = cw.urllib_transport("PUT", "https://x.test/api/x",
                                       {"Authorization": "Bearer t"}, b'{"a":1}')
    assert (status, text) == (201, '{"created": 1}')
    assert captured["method"] == "PUT"
    assert captured["body"] == b'{"a":1}'
