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
    derive_reply_all,
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
    # shape parity with a real send: same routing keys, empty — callers never branch
    assert result["message_id"] == "" and result["thread_id"] == ""


def test_send_invokes_gog_and_parses_result():
    seen = {}

    def fake_runner(cmd, capture_output, text, timeout):
        seen["cmd"] = cmd
        seen["timeout"] = timeout
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
    def fake_runner(cmd, capture_output, text, timeout):
        return SimpleNamespace(returncode=1, stdout="", stderr="invalid_grant: bad token")

    with pytest.raises(AgentEmailError, match="invalid_grant"):
        send(IDENT, to="a@x.com", subject="s", body_text="x\n", runner=fake_runner)


def test_send_timeout_raises_instead_of_hanging_the_turn():
    def hung_runner(cmd, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)

    with pytest.raises(AgentEmailError, match="timed out"):
        send(IDENT, to="a@x.com", subject="s", body_text="x\n", runner=hung_runner)


# --------------------------------------------------------------------------------------
# reply-all derivation (§1b rule 3 — raw reads hide Cc and drop cc'd people)
# --------------------------------------------------------------------------------------

def _thread_json(message_id="m1", frm="Dr. C <c@partner.org>",
                 to="ace@dimagi-ai.com, hal@dimagi-ai.com",
                 cc="ops@partner.org"):
    return json.dumps({"thread": {"messages": [{
        "id": message_id,
        "payload": {"headers": [
            {"name": "From", "value": frm},
            {"name": "To", "value": to},
            {"name": "Cc", "value": cc},
        ]},
    }]}})


def _reply_runner(stdout, returncode=0):
    def runner(cmd, capture_output, text, timeout):
        assert cmd[:3] == ["gog", "gmail", "read"] and "--json" in cmd
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")
    return runner


def test_derive_reply_all_sender_to_and_others_cc_excluding_self():
    to, cc, msg_id = derive_reply_all(IDENT, message_id="m1",
                                      runner=_reply_runner(_thread_json()))
    assert to == "c@partner.org"
    # hal (self) and the sender are excluded; the other To recipient + Cc survive
    assert cc == "ace@dimagi-ai.com, ops@partner.org"
    assert msg_id == "m1"


def test_derive_reply_all_missing_from_header_raises():
    bad = _thread_json(frm="")
    with pytest.raises(AgentEmailError, match="no From header"):
        derive_reply_all(IDENT, message_id="m1", runner=_reply_runner(bad))


def test_derive_reply_all_read_failure_raises():
    with pytest.raises(AgentEmailError, match="could not read"):
        derive_reply_all(IDENT, message_id="m1", runner=_reply_runner("", returncode=1))


def test_derive_reply_all_requires_exactly_one_id():
    with pytest.raises(AgentEmailError, match="exactly one"):
        derive_reply_all(IDENT, runner=_reply_runner(_thread_json()))
    with pytest.raises(AgentEmailError, match="exactly one"):
        derive_reply_all(IDENT, thread_id="t1", message_id="m1",
                         runner=_reply_runner(_thread_json()))


def _multi_message_thread():
    """A thread where the LATEST message is the agent's own send — reply-all must
    target the latest NON-self message (echo's live lesson), not the agent's."""
    def msg(mid, frm, to, cc=""):
        return {"id": mid, "payload": {"headers": [
            {"name": "From", "value": frm},
            {"name": "To", "value": to},
            {"name": "Cc", "value": cc},
        ]}}
    return json.dumps({"thread": {"messages": [
        msg("m1", "Dr. C <c@partner.org>", "hal@dimagi-ai.com", "ops@partner.org"),
        msg("m2", "Colleague <k@partner.org>", "hal@dimagi-ai.com, c@partner.org"),
        msg("m3", "Hal <hal@dimagi-ai.com>", "k@partner.org"),
    ]}})


def test_derive_reply_all_thread_mode_targets_latest_non_self_message():
    to, cc, msg_id = derive_reply_all(IDENT, thread_id="t1",
                                      runner=_reply_runner(_multi_message_thread()))
    assert to == "k@partner.org"          # sender of the latest NON-hal message (m2)
    assert cc == "c@partner.org"          # m2's other recipient, minus hal + sender
    assert msg_id == "m2"                 # threading targets m2, NOT the thread id


# --------------------------------------------------------------------------------------
# mark-read (via gog thread modify — NEVER the macOS Keychain, dimagi-internal/ace#827)
# --------------------------------------------------------------------------------------

def test_mark_read_shells_gog_thread_modify_per_thread():
    calls = []

    def fake_runner(cmd, capture_output, text, timeout):
        calls.append(cmd)
        if cmd[4] == "bad2":
            return SimpleNamespace(returncode=1, stdout="", stderr="not found")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    results = mark_read(IDENT, ["t1", "bad2"], runner=fake_runner)
    assert results[0] == {"thread_id": "t1", "ok": True, "error": ""}
    assert results[1]["ok"] is False and "not found" in results[1]["error"]
    assert calls[0] == ["gog", "gmail", "thread", "modify", "t1", "--remove", "UNREAD",
                        "--account", "hal@dimagi-ai.com", "--client", "hal"]


def test_mark_read_never_touches_the_keychain():
    """The #827 hang class: `security find-generic-password` blocks forever on a GUI
    prompt in non-interactive shells. The runner must only ever see gog commands."""
    def fake_runner(cmd, capture_output, text, timeout):
        assert cmd[0] == "gog", f"non-gog subprocess in mark_read: {cmd}"
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    mark_read(IDENT, ["t1", "t2"], runner=fake_runner)


def test_mark_read_timeout_is_per_thread_and_keeps_going():
    def flaky_runner(cmd, capture_output, text, timeout):
        if cmd[4] == "slow":
            raise subprocess.TimeoutExpired(cmd, timeout)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    results = mark_read(IDENT, ["slow", "t2"], runner=flaky_runner)
    assert results[0]["ok"] is False and "timed out" in results[0]["error"]
    assert results[1]["ok"] is True


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


def _provision_repo(tmp_path, op_ref="op://AI-Agents/Hal - gog OAuth client/notesPlain"):
    """An agent repo whose config/secrets.yaml declares the gog client for provisioning."""
    repo = _agent_repo(tmp_path)
    (repo / "config" / "secrets.yaml").write_text(
        "secrets:\n"
        "  - name: hal gog OAuth client JSON\n"
        f'    op: "{op_ref}"\n'
        '    target: "~/Library/Application Support/gogcli/credentials-hal.json"\n'
    )
    return repo


def test_preflight_missing_creds_routes_through_provision_when_declared(tmp_path, monkeypatch):
    # Declared + 1Password item resolves -> tell the user to `canopy provision`, not hand-copy.
    from orchestrator import provision
    monkeypatch.setattr(provision, "_op_read", lambda ref: "{\"client_id\": \"x\"}")
    ident = EmailIdentity(slug="hal", account="hal@dimagi-ai.com", client="hal",
                          repo=_provision_repo(tmp_path))
    ok, lines = preflight(ident, gog_dir=_gog_home(tmp_path, creds=False))
    assert not ok
    joined = "\n".join(lines)
    assert "canopy provision" in joined
    assert "gog login hal@dimagi-ai.com --client hal" in joined
    assert "Copy hal's OWN OAuth client JSON there" not in joined  # not the manual fallback


def test_preflight_missing_1password_item_is_the_named_blocker(tmp_path, monkeypatch):
    # Declared but the 1Password item doesn't resolve -> that IS the blocker, named exactly.
    from orchestrator import provision
    def boom(ref):
        raise provision.ProvisionError(f"`op read {ref}` failed: isn't an item")
    monkeypatch.setattr(provision, "_op_read", boom)
    ident = EmailIdentity(slug="hal", account="hal@dimagi-ai.com", client="hal",
                          repo=_provision_repo(tmp_path))
    ok, lines = preflight(ident, gog_dir=_gog_home(tmp_path, creds=False))
    assert not ok
    joined = "\n".join(lines)
    assert "op://AI-Agents/Hal - gog OAuth client/notesPlain" in joined
    assert "canopy provision" in joined
    assert "isn't in 1Password yet" in joined


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
