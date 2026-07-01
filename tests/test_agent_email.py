"""Tests for the shared agent email engine (canopy email — shared-gog-gdrive.md §3)."""
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.agent_email import (
    AgentEmailError,
    EmailIdentity,
    build_send_command,
    mark_read,
    normalize,
    parse_send_result,
    preflight,
    resolve_email_identity,
    send,
    to_html,
)


# --------------------------------------------------------------------------------------
# identity resolution
# --------------------------------------------------------------------------------------

def _agent_repo(tmp_path, *, email="hal@dimagi-ai.com", gog_client=None, slug="hal"):
    repo = tmp_path / slug
    (repo / ".claude-plugin").mkdir(parents=True)
    (repo / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": slug}))
    agent = {"name": slug.title(), "email": email}
    if gog_client is not None:
        agent["gog_client"] = gog_client
    (repo / "config").mkdir()
    (repo / "config" / "agent.json").write_text(json.dumps(agent))
    return repo


def test_resolve_identity_from_agent_json(tmp_path):
    repo = _agent_repo(tmp_path, gog_client="hal-oauth")
    ident = resolve_email_identity(repo)
    assert ident.slug == "hal"
    assert ident.account == "hal@dimagi-ai.com"
    assert ident.client == "hal-oauth"


def test_resolve_identity_client_defaults_to_slug(tmp_path):
    ident = resolve_email_identity(_agent_repo(tmp_path))
    assert ident.client == "hal"


def test_resolve_identity_requires_mailbox(tmp_path):
    repo = _agent_repo(tmp_path, email="")
    with pytest.raises(AgentEmailError, match="config/agent.json"):
        resolve_email_identity(repo)


def test_resolve_identity_requires_agent_repo(tmp_path):
    with pytest.raises(AgentEmailError):
        resolve_email_identity(tmp_path)  # no .claude-plugin/plugin.json


# --------------------------------------------------------------------------------------
# body shaping (the echo-proven wrapper behavior)
# --------------------------------------------------------------------------------------

def test_normalize_collapses_hard_wrapped_paragraphs():
    text = "one line\nsplit over\nthree lines\n\nsecond para\n"
    assert normalize(text) == "one line split over three lines\n\nsecond para\n"


def test_normalize_keeps_bullets_as_lines():
    text = "intro\n\n- alpha\n- beta\n1. gamma\n"
    assert normalize(text) == "intro\n\n- alpha\n- beta\n1. gamma\n"


def test_to_html_paragraphs_and_bullets():
    out = to_html("hello there\n\n- one\n- two\n")
    assert "<p>hello there</p>" in out
    assert "<ul><li>one</li><li>two</li></ul>" in out


def test_to_html_linkifies_and_escapes():
    out = to_html("see https://example.com/x?a=1 & <tags>\n")
    assert '<a href="https://example.com/x?a=1">' in out
    assert "&lt;tags&gt;" in out
    assert "&amp;" in out


# --------------------------------------------------------------------------------------
# send
# --------------------------------------------------------------------------------------

IDENT = EmailIdentity(slug="hal", account="hal@dimagi-ai.com", client="hal")


def test_build_send_command_full():
    cmd = build_send_command(
        IDENT, to="a@x.com", subject="Re: hi", plain_path="/tmp/p.txt",
        html_body="<html/>", cc="c@x.com", reply_to_message_id="m123",
    )
    assert cmd[:3] == ["gog", "gmail", "send"]
    assert ("--account", "hal@dimagi-ai.com") == (cmd[3], cmd[4])
    assert ("--client", "hal") == (cmd[5], cmd[6])
    assert "--json" in cmd
    assert cmd[cmd.index("--cc") + 1] == "c@x.com"
    assert cmd[cmd.index("--reply-to-message-id") + 1] == "m123"


def test_parse_send_result_normalizes_key_variants():
    assert parse_send_result('{"id": "m1", "threadId": "t1"}') == {
        "message_id": "m1", "thread_id": "t1", "raw": {"id": "m1", "threadId": "t1"}}
    r = parse_send_result('{"message_id": "m2", "thread_id": "t2"}')
    assert (r["message_id"], r["thread_id"]) == ("m2", "t2")
    r = parse_send_result("not json")
    assert (r["message_id"], r["thread_id"]) == ("", "")


def test_send_dry_run_never_invokes_gog():
    def boom(*a, **k):
        raise AssertionError("runner must not be called on dry-run")
    result = send(IDENT, to="a@x.com", subject="s",
                  body_text="hello\nworld\n", dry_run=True, runner=boom)
    assert result["dry_run"] is True
    assert result["account"] == "hal@dimagi-ai.com"
    assert result["plain"] == "hello world\n"
    assert "<p>hello world</p>" in result["html"]


def test_send_invokes_gog_and_parses_result():
    seen = {}

    def fake_runner(cmd, capture_output, text):
        seen["cmd"] = cmd
        seen["plain"] = Path(cmd[cmd.index("--body-file") + 1]).read_text()
        return SimpleNamespace(returncode=0, stdout='{"id": "m9", "threadId": "t9"}', stderr="")

    result = send(IDENT, to="a@x.com", subject="s", body_text="para one\nwrapped\n",
                  runner=fake_runner)
    assert result == {"message_id": "m9", "thread_id": "t9",
                      "raw": {"id": "m9", "threadId": "t9"}}
    assert seen["plain"] == "para one wrapped\n"
    # the temp plain-text file is cleaned up after the send
    assert not os.path.exists(seen["cmd"][seen["cmd"].index("--body-file") + 1])


def test_send_failure_raises_with_stderr():
    def fake_runner(cmd, capture_output, text):
        return SimpleNamespace(returncode=1, stdout="", stderr="invalid_grant: bad token")

    with pytest.raises(AgentEmailError, match="invalid_grant"):
        send(IDENT, to="a@x.com", subject="s", body_text="x\n", runner=fake_runner)


# --------------------------------------------------------------------------------------
# mark-read
# --------------------------------------------------------------------------------------

def test_mark_read_posts_unread_removal_per_thread():
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_opener(req):
        calls.append(req)
        if "bad" in req.full_url:
            raise OSError("HTTP 404")
        return FakeResponse()

    results = mark_read(IDENT, ["t1", "bad2"], token="tok", opener=fake_opener)
    assert results[0] == {"thread_id": "t1", "ok": True, "error": ""}
    assert results[1]["ok"] is False and "404" in results[1]["error"]
    req = calls[0]
    assert req.full_url.endswith("/threads/t1/modify")
    assert req.get_header("Authorization") == "Bearer tok"
    assert json.loads(req.data) == {"removeLabelIds": ["UNREAD"]}


# --------------------------------------------------------------------------------------
# preflight
# --------------------------------------------------------------------------------------

def _gog_home(tmp_path, *, creds=True, mapped=True):
    home = tmp_path / "gogcli"
    home.mkdir()
    if creds:
        (home / "credentials-hal.json").write_text('{"client_id": "x", "client_secret": "y"}')
    if mapped:
        (home / "config.json").write_text(
            json.dumps({"account_clients": {"hal@dimagi-ai.com": "hal"}}))
    return str(home)


def test_preflight_missing_creds_gives_exact_login_remediation(tmp_path):
    ok, lines = preflight(IDENT, gog_dir=_gog_home(tmp_path, creds=False))
    assert not ok
    joined = "\n".join(lines)
    assert "credentials-hal.json" in joined
    assert "gog login hal@dimagi-ai.com --client hal --services" in joined


def test_preflight_unmapped_account(tmp_path):
    ok, lines = preflight(IDENT, gog_dir=_gog_home(tmp_path, mapped=False))
    assert not ok
    assert any("account_clients" in ln for ln in lines)


def test_preflight_live_check_passes(tmp_path):
    def fake_runner(cmd, capture_output, text, timeout):
        assert cmd[:3] == ["gog", "gmail", "search"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    ok, lines = preflight(IDENT, gog_dir=_gog_home(tmp_path), runner=fake_runner)
    assert ok
    assert "gog Gmail ready" in lines[0]


def test_preflight_bad_token_names_login_fix(tmp_path):
    def fake_runner(cmd, capture_output, text, timeout):
        return SimpleNamespace(returncode=1, stdout="", stderr="token expired or revoked")

    ok, lines = preflight(IDENT, gog_dir=_gog_home(tmp_path), runner=fake_runner)
    assert not ok
    assert any("gog login hal@dimagi-ai.com --client hal" in ln for ln in lines)


def test_preflight_api_not_enabled_self_heal(tmp_path):
    stderr = ("Error: Gmail API has not been used in project 123 before or it is disabled. "
              "Enable it by visiting https://console.developers.google.com/apis/api/gmail/overview?project=123 "
              "then retry.")

    def fake_runner(cmd, capture_output, text, timeout):
        return SimpleNamespace(returncode=1, stdout="", stderr=stderr)

    ok, lines = preflight(IDENT, gog_dir=_gog_home(tmp_path), runner=fake_runner)
    assert not ok
    joined = "\n".join(lines)
    assert "NOT a token problem" in joined
    assert "https://console.developers.google.com" in joined
