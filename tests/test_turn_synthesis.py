"""Tests for the canonical turn-synthesis reducer (shared by share-session + harvest)."""
import json

from orchestrator import turn_synthesis as ts


def _write(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


def test_synthesize_pairs_prompt_with_final_reply(tmp_path):
    p = tmp_path / "s.jsonl"
    _write(p, [
        {"type": "system", "subtype": "init", "session_id": "sess-123"},
        {"type": "user", "message": {"content": "do the thing"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "intermediate"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "FINAL A"}]}},
        {"type": "user", "message": {"content": "next"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "FINAL B"}]}},
    ])
    session_id, turns = ts.synthesize(p)
    assert session_id == "sess-123"
    assert [(t.prompt, t.response) for t in turns] == [
        ("do the thing", "FINAL A"),   # latest assistant message wins
        ("next", "FINAL B"),
    ]


def test_synthesize_drops_noise_and_tool_results(tmp_path):
    p = tmp_path / "s.jsonl"
    _write(p, [
        {"type": "user", "message": {"content": "real intent"}},
        {"type": "user", "message": {"content": "<system-reminder>noise</system-reminder>"}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
        {"type": "user", "message": {"content": "[Request interrupted by user]"}},
    ])
    _session_id, turns = ts.synthesize(p)
    assert [t.prompt for t in turns] == ["real intent"]
    assert turns[0].response == "ok"


def test_synthesize_renders_slash_command(tmp_path):
    p = tmp_path / "s.jsonl"
    _write(p, [
        {"type": "user", "message": {"content": "<command-name>/loop</command-name><command-args>5m /foo</command-args>"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "looping"}]}},
    ])
    _session_id, turns = ts.synthesize(p)
    assert turns[0].prompt == "/loop 5m /foo"


def test_synthesize_skips_sidechain(tmp_path):
    p = tmp_path / "s.jsonl"
    _write(p, [
        {"type": "user", "message": {"content": "main prompt"}},
        {"type": "assistant", "isSidechain": True, "message": {"content": [{"type": "text", "text": "subagent chatter"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "real reply"}]}},
    ])
    _session_id, turns = ts.synthesize(p)
    assert turns[0].response == "real reply"


def test_synthesize_trailing_prompt_without_reply(tmp_path):
    p = tmp_path / "s.jsonl"
    _write(p, [
        {"type": "user", "message": {"content": "first"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "answer"}]}},
        {"type": "user", "message": {"content": "dangling"}},
    ])
    _session_id, turns = ts.synthesize(p)
    assert [(t.prompt, t.response) for t in turns] == [("first", "answer"), ("dangling", "")]


def test_to_share_jsonl_roundtrips(tmp_path):
    turns = [ts.Turn("p1", "r1"), ts.Turn("p2", ""), ts.Turn("p3", "r3")]
    blob, n = ts.to_share_jsonl("sid", turns)
    # 3 user lines + 2 assistant lines (the empty response emits no assistant line)
    assert n == 5
    lines = [json.loads(x) for x in blob.decode().splitlines()]
    assert lines[0] == {"type": "system", "subtype": "init", "session_id": "sid"}
    kinds = [(e["type"], e["message"].get("content")) for e in lines[1:]]
    assert kinds[0] == ("user", "p1")
    assert lines[2]["type"] == "assistant"
    assert lines[2]["message"]["content"][0]["text"] == "r1"
    # p2 has no reply → next line is the p3 user line
    assert lines[3]["message"]["content"] == "p2"
    assert lines[4]["message"]["content"] == "p3"


def test_to_share_jsonl_strips_nul_bytes(tmp_path):
    blob, _n = ts.to_share_jsonl("sid", [ts.Turn("pro\x00mpt", "resp\x00onse")])
    assert "\x00" not in blob.decode()


def test_iter_messages_keeps_every_assistant_block(tmp_path):
    p = tmp_path / "s.jsonl"
    _write(p, [
        {"type": "user", "message": {"content": "go"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "block one"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "block two"}]}},
    ])
    seq = ts.iter_messages(p)
    assert seq == [("U", "go"), ("A", "block one"), ("A", "block two")]
