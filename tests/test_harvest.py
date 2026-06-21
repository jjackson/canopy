"""Tests for the harvest corpus engine (cross-user, origin-anchored, blindness-flagging)."""
import json

from orchestrator.harvest import (
    assemble_corpus,
    find_initiative_sessions,
    human_messages,
    user_session_roots,
)


def _session(path, prompts):
    """Write a minimal Claude jsonl with the given human prompts."""
    lines = [json.dumps({"type": "user", "message": {"content": p}}) for p in prompts]
    path.write_text("\n".join(lines) + "\n")


def _fake_machine(tmp_path):
    """Two macOS users; one readable, mimic the cross-user setup."""
    users = tmp_path / "Users"
    # user A: has a ddd initiative origin + recent
    a = users / "ace" / ".claude" / "projects" / "-x-emdash-ddd-origin"
    a.mkdir(parents=True)
    _session(a / "old.jsonl", ["build the demo-driven-development video pipeline", "keep going"])
    b = users / "ace" / ".claude" / "projects" / "-x-emdash-other"
    b.mkdir(parents=True)
    _session(b / "x.jsonl", ["totally unrelated task about billing"])
    # user J: has the EARLIEST ddd session (origin lives on the other account)
    j = users / "jjk" / ".claude" / "projects" / "-x-emdash-ddd-seed"
    j.mkdir(parents=True)
    _session(j / "seed.jsonl", ["I want to record demo videos / synthetic walkthroughs"])
    return users


def _roots(users):
    return [
        {"user": "ace", "path": str(users / "ace" / ".claude" / "projects"), "readable": True},
        {"user": "jjk", "path": str(users / "jjk" / ".claude" / "projects"), "readable": True},
    ]


def test_finds_across_users_oldest_first(tmp_path):
    users = _fake_machine(tmp_path)
    roots = _roots(users)
    # make the jjk seed the OLDEST
    import os, time
    seed = users / "jjk" / ".claude" / "projects" / "-x-emdash-ddd-seed" / "seed.jsonl"
    old = users / "ace" / ".claude" / "projects" / "-x-emdash-ddd-origin" / "old.jsonl"
    os.utime(seed, (time.time() - 3000, time.time() - 3000))
    os.utime(old, (time.time() - 1000, time.time() - 1000))
    refs = find_initiative_sessions("ddd", ["ddd", "demo-driven", "walkthrough", "demo video"], roots=roots)
    users_in_order = [r.user for r in refs]
    assert users_in_order[0] == "jjk", "origin (oldest) must come first, and it's on the OTHER user"
    assert "ace" in users_in_order
    # the unrelated billing session is excluded
    assert all("other" not in r.project for r in refs)


def test_corpus_flags_half_blind(tmp_path):
    users = _fake_machine(tmp_path)
    roots = _roots(users)
    roots[1]["readable"] = False  # jjk unreadable
    corpus = assemble_corpus("ddd", ["ddd", "demo", "walkthrough"], roots=roots)
    assert corpus["confidence"] == "half-blind"
    assert corpus["unreadable_users"] == ["jjk"]


def test_corpus_whole_when_all_readable(tmp_path):
    users = _fake_machine(tmp_path)
    corpus = assemble_corpus("ddd", ["ddd", "demo", "walkthrough"], roots=_roots(users))
    assert corpus["confidence"] == "whole-corpus"
    assert corpus["by_user"].get("jjk", 0) >= 1 and corpus["by_user"].get("ace", 0) >= 1
    assert corpus["span"] is not None


def test_human_messages_filters_noise(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join([
        json.dumps({"type": "user", "message": {"content": "real intent here"}}),
        json.dumps({"type": "user", "message": {"content": "<system-reminder>noise</system-reminder>"}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}),
        json.dumps({"type": "user", "message": {"content": "more steering"}}),
    ]) + "\n")
    msgs = human_messages(str(p))
    assert msgs == ["real intent here", "more steering"]


def test_user_session_roots_real_machine():
    # smoke: on the real machine this should at least find acedimagi
    roots = user_session_roots()
    assert any(r["user"] == "acedimagi" for r in roots)
