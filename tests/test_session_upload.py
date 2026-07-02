"""Unit tests for orchestrator.session_upload — the packageable transcript uploader.

No network: the canopy_web Transport is injected, and turn_synthesis timing is
stubbed so the tests don't depend on transcript-parsing internals.
"""
import json

import pytest

from orchestrator import session_upload
from orchestrator.canopy_web import CanopyError


def _recorder(status=201, body=None):
    calls = []
    payload = json.dumps(body if body is not None else {"slug": "sess-slug", "share_token": "tok123"})

    def transport(method, url, headers, data):
        calls.append({"method": method, "url": url, "headers": headers, "data": data})
        return status, payload

    return transport, calls


def test_upload_full_posts_multipart_and_returns_link(tmp_path, monkeypatch):
    monkeypatch.setattr(session_upload.turn_synthesis, "timespan", lambda p: (None, None))
    monkeypatch.setattr(session_upload.turn_synthesis, "active_seconds", lambda p: 0)
    src = tmp_path / "abc-session-id.jsonl"
    src.write_bytes(b'{"type":"user"}\n{"type":"assistant"}\n')

    transport, calls = _recorder()
    result = session_upload.upload_transcript(
        src, title="My turn", full=True,
        base_url="https://x.test", token="t", transport=transport,
    )

    assert result["slug"] == "sess-slug"
    assert result["share_token"] == "tok123"
    # cli_session_id derives from the filename stem on the full path
    assert result["cli_session_id"] == "abc-session-id"
    call = calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://x.test/api/sessions/upload"
    assert call["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert call["headers"]["Authorization"] == "Bearer t"
    # the raw bytes ride in the multipart body, and the title field is present
    assert b'{"type":"user"}' in call["data"]
    assert b'name="title"' in call["data"]


def test_upload_reduced_uses_turn_synthesis(tmp_path, monkeypatch):
    monkeypatch.setattr(session_upload.turn_synthesis, "timespan", lambda p: (None, None))
    monkeypatch.setattr(session_upload.turn_synthesis, "active_seconds", lambda p: 0)
    monkeypatch.setattr(session_upload.turn_synthesis, "synthesize",
                        lambda p: ("real-session-id", ["turn"]))
    monkeypatch.setattr(session_upload.turn_synthesis, "to_share_jsonl",
                        lambda sid, turns: (b'{"reduced":true}\n', 1))
    src = tmp_path / "whatever.jsonl"
    src.write_bytes(b'{"lots":"of noise"}\n')

    transport, calls = _recorder()
    result = session_upload.upload_transcript(
        src, title="Reduced turn",
        base_url="https://x.test", token="t", transport=transport,
    )
    # cli_session_id comes from synthesize(), NOT the filename, on the reduced path
    assert result["cli_session_id"] == "real-session-id"
    assert b'{"reduced":true}' in calls[0]["data"]
    assert b'{"lots":"of noise"}' not in calls[0]["data"]  # raw noise never uploaded


def test_upload_raises_on_non_2xx(tmp_path, monkeypatch):
    monkeypatch.setattr(session_upload.turn_synthesis, "timespan", lambda p: (None, None))
    monkeypatch.setattr(session_upload.turn_synthesis, "active_seconds", lambda p: 0)
    src = tmp_path / "x.jsonl"
    src.write_bytes(b"{}\n")
    transport, _ = _recorder(status=403, body={"detail": "nope"})
    with pytest.raises(CanopyError):
        session_upload.upload_transcript(src, title="t", full=True,
                                         base_url="https://x.test", token="t", transport=transport)
