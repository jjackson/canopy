"""Tests for the shared agent gdoc engine (canopy gdoc — shared-gog-gdrive.md §5)."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from orchestrator.agent_gdoc import (
    AgentGdocError,
    GdocIdentity,
    build_share_command,
    build_upload_command,
    md_to_html,
    parse_upload_result,
    publish,
    resolve_gdoc_identity,
    verify_permissions,
)


# --------------------------------------------------------------------------------------
# identity resolution
# --------------------------------------------------------------------------------------

def _agent_repo(tmp_path, *, email="hal@dimagi-ai.com", gog_client=None, slug="hal",
                root_folder=None, share_default=None):
    repo = tmp_path / slug
    (repo / ".claude-plugin").mkdir(parents=True)
    (repo / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": slug}))
    agent = {"name": slug.title(), "email": email}
    if gog_client is not None:
        agent["gog_client"] = gog_client
    if root_folder is not None:
        agent["gdrive_root_folder"] = root_folder
    if share_default is not None:
        agent["gdrive_share_default"] = share_default
    (repo / "config").mkdir()
    (repo / "config" / "agent.json").write_text(json.dumps(agent))
    return repo


def test_resolve_identity_from_agent_json(tmp_path):
    repo = _agent_repo(tmp_path, gog_client="hal-oauth", root_folder="FOLDER123",
                       share_default="anyone")
    ident = resolve_gdoc_identity(repo)
    assert ident.slug == "hal"
    assert ident.account == "hal@dimagi-ai.com"
    assert ident.client == "hal-oauth"
    assert ident.root_folder == "FOLDER123"
    assert ident.share_default == "anyone"


def test_resolve_identity_defaults(tmp_path):
    ident = resolve_gdoc_identity(_agent_repo(tmp_path))
    assert ident.client == "hal"           # client defaults to slug
    assert ident.root_folder == ""         # optional
    assert ident.share_default == "domain"  # safe default


def test_resolve_identity_rejects_bad_share_default(tmp_path):
    ident = resolve_gdoc_identity(_agent_repo(tmp_path, share_default="everyone"))
    assert ident.share_default == "domain"  # unknown -> safe default


def test_resolve_identity_requires_mailbox(tmp_path):
    with pytest.raises(AgentGdocError, match="config/agent.json"):
        resolve_gdoc_identity(_agent_repo(tmp_path, email=""))


# --------------------------------------------------------------------------------------
# markdown -> html
# --------------------------------------------------------------------------------------

def test_md_to_html_headings_and_links():
    out = md_to_html("# Title\n\nSome **bold** and a [link](https://x.com).")
    assert "<h1>Title</h1>" in out
    assert "<strong>bold</strong>" in out
    assert '<a href="https://x.com">link</a>' in out


def test_md_to_html_lists():
    out = md_to_html("- one\n- two\n\n1. first\n2. second")
    assert "<ul><li>one</li><li>two</li></ul>" in out
    assert "<ol><li>first</li><li>second</li></ol>" in out


def test_md_to_html_escapes_html():
    assert "&lt;script&gt;" in md_to_html("a <script> tag")


# --------------------------------------------------------------------------------------
# gog command construction
# --------------------------------------------------------------------------------------

def _ident(**kw):
    base = dict(slug="hal", account="hal@dimagi-ai.com", client="hal")
    base.update(kw)
    return GdocIdentity(**base)


def test_build_upload_command_create():
    cmd = build_upload_command(_ident(), html_path="/tmp/x.html", name="My Doc",
                               parent="FOLDER123", replace=None)
    assert cmd[:3] == ["gog", "drive", "upload"]
    assert "--convert-to" in cmd and cmd[cmd.index("--convert-to") + 1] == "doc"
    assert cmd[cmd.index("--parent") + 1] == "FOLDER123"
    assert cmd[cmd.index("--name") + 1] == "My Doc"
    assert cmd[cmd.index("--account") + 1] == "hal@dimagi-ai.com"


def test_build_upload_command_replace_has_no_convert():
    cmd = build_upload_command(_ident(), html_path="/tmp/x.html", name=None,
                               parent="IGNORED", replace="DOCID")
    assert "--convert-to" not in cmd  # gog rejects --replace + --convert
    assert "--parent" not in cmd      # create-only
    assert cmd[cmd.index("--replace") + 1] == "DOCID"
    assert cmd[cmd.index("--mime-type") + 1] == "text/html"


def test_build_share_command_domain():
    cmd = build_share_command(_ident(), "DOCID", share="domain", email=None)
    assert cmd[cmd.index("--to") + 1] == "domain"
    assert cmd[cmd.index("--domain") + 1] == "dimagi.com"
    assert cmd[cmd.index("--role") + 1] == "reader"


def test_build_share_command_user_requires_email():
    with pytest.raises(AgentGdocError, match="share-email"):
        build_share_command(_ident(), "DOCID", share="user", email=None)


def test_parse_upload_result_unwraps_gog_file_envelope():
    # gog v0.12 wraps the created file under a "file" key (confirmed live) — the shape a
    # naive mock misses. This is the exact payload that broke the first live smoke.
    stdout = json.dumps({"file": {"id": "D1", "webViewLink": "u", "mimeType": "…document"}})
    out = parse_upload_result(stdout)
    assert out["id"] == "D1"
    assert out["url"] == "u"


def test_parse_upload_result_liberal_keys():
    # unwrapped top-level id/link still works (defensive against a gog shape change)
    assert parse_upload_result(json.dumps({"id": "D1", "webViewLink": "u"}))["id"] == "D1"
    # falls back to a constructed url when no link key is present
    assert parse_upload_result(json.dumps({"file": {"id": "D2"}}))["url"].endswith("/D2/edit")
    # non-JSON is surfaced as raw, not crashed on
    assert parse_upload_result("boom")["id"] == ""


# --------------------------------------------------------------------------------------
# publish (with a fake gog runner — no network)
# --------------------------------------------------------------------------------------

class _FakeGog:
    """Records commands; returns queued responses by (verb) — upload/share/permissions."""

    def __init__(self, *, upload_ok=True, share_ok=True, perm_type="domain"):
        self.calls = []
        self.upload_ok = upload_ok
        self.share_ok = share_ok
        self.perm_type = perm_type

    def __call__(self, cmd, capture_output=True, text=True, timeout=None):
        self.calls.append(cmd)
        verb = cmd[2]
        if verb == "upload":
            if not self.upload_ok:
                return SimpleNamespace(returncode=1, stdout="", stderr="nope")
            # gog's REAL shape: the file is wrapped under a "file" envelope (confirmed live).
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"file": {"id": "DOC1", "webViewLink": "URL1"}}), stderr="")
        if verb == "share":
            # gog's real share payload: {"link", "permission": {...}, "permissionId"}.
            return SimpleNamespace(
                returncode=0 if self.share_ok else 1,
                stdout=json.dumps({"permission": {"type": "domain", "domain": "dimagi.com"}}),
                stderr="x")
        if verb == "permissions":
            # gog's real permissions payload: list under a "permissions" key.
            perm = {"type": self.perm_type, "domain": "dimagi.com"}
            return SimpleNamespace(
                returncode=0, stdout=json.dumps({"permissions": [perm]}), stderr="")
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")


def test_publish_create_shares_and_verifies(tmp_path):
    md = tmp_path / "d.md"
    md.write_text("# Hi\n\nbody")
    gog = _FakeGog()
    res = publish(_ident(), name="Doc", parent="F1", md_path=str(md), share="domain",
                  runner=gog)
    assert res["id"] == "DOC1"
    assert res["url"] == "URL1"
    assert res["shared"] == "domain"
    assert res["verified"] is True
    verbs = [c[2] for c in gog.calls]
    assert verbs == ["upload", "share", "permissions"]  # created, shared, verified


def test_publish_reports_unverified_when_permission_missing(tmp_path):
    md = tmp_path / "d.md"
    md.write_text("body")
    gog = _FakeGog(perm_type="anyone")  # asked for domain, readback shows only anyone
    res = publish(_ident(), name="Doc", parent="F1", md_path=str(md), share="domain",
                  runner=gog)
    assert res["verified"] is False


def test_publish_replace_preserves_share(tmp_path):
    md = tmp_path / "d.md"
    md.write_text("body")
    gog = _FakeGog()
    res = publish(_ident(), name=None, parent=None, md_path=str(md), share="domain",
                  replace="DOCX", runner=gog)
    assert res["shared"] == "preserved"
    verbs = [c[2] for c in gog.calls]
    assert verbs == ["upload"]  # no re-share on replace


def test_publish_create_requires_name_and_parent(tmp_path):
    md = tmp_path / "d.md"
    md.write_text("body")
    with pytest.raises(AgentGdocError, match="required for a new doc"):
        publish(_ident(), name=None, parent=None, md_path=str(md), share="none")


def test_publish_dry_run_touches_nothing(tmp_path):
    md = tmp_path / "d.md"
    md.write_text("# T\n\nbody")
    gog = _FakeGog()
    res = publish(_ident(), name="Doc", parent="F1", md_path=str(md), share="domain",
                  dry_run=True, runner=gog)
    assert res["dry_run"] is True
    assert gog.calls == []  # never shelled out
    assert res["upload_cmd"][:3] == ["gog", "drive", "upload"]


def test_publish_raises_on_upload_failure(tmp_path):
    md = tmp_path / "d.md"
    md.write_text("body")
    with pytest.raises(AgentGdocError, match="upload failed"):
        publish(_ident(), name="Doc", parent="F1", md_path=str(md), share="domain",
                runner=_FakeGog(upload_ok=False))
