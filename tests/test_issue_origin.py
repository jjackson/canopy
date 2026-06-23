"""canopy.origin/v1 — provenance records for architect-routed issues."""
import os
from orchestrator import issue_origin as io


def _rec(tmp, **over):
    r = io.build_record(
        repo="jjackson/canopy", initiative="ddd", ledger="hal/ledgers/ddd.md",
        created="2026-06-23", confidence="high",
        mandate="Encode the DDD operating model into the ddd skills.",
        done_when="A cold /canopy:ddd run follows it unprompted.",
        intent="DDD = a general methodology where one narrative does triple duty.",
        evidence=[{"claim": "never review PRs", "session": str(tmp / "s1.jsonl")}],
        sessions_scanned=331, cross_user=True,
        drilled=[str(tmp / "s1.jsonl"), str(tmp / "missing.jsonl")],
        number=42,
    )
    r["title"] = "Codify the DDD operating model"
    r.update(over)
    return r


def test_clean_issue_body_has_no_local_paths(tmp_path):
    """The PORTABLE issue body must never leak machine-local session paths or yaml."""
    body = io.clean_issue_body(_rec(tmp_path))
    assert "Encode the DDD operating model" in body
    assert "Done when:" in body
    assert "canopy issue context jjackson/canopy#42" in body
    assert "/Users/" not in body and ".jsonl" not in body        # no local pointers
    assert "schema:" not in body and "drilled" not in body        # no yaml dump


def test_save_load_roundtrip_and_dedup(tmp_path, monkeypatch):
    monkeypatch.setattr(io, "_store_dir", lambda: tmp_path / "issues")
    rec = _rec(tmp_path)
    io.save_local(rec)
    assert io.load_local("jjackson/canopy", 42)["intent"].startswith("DDD =")
    assert io.find_existing_issue_number("jjackson/canopy", "Codify the DDD operating model") == 42
    assert io.find_existing_issue_number("jjackson/canopy", "something else") is None


def test_record_keeps_only_pointers_not_transcripts(tmp_path):
    rec = _rec(tmp_path)
    # the record references sessions by path; it must not embed their contents
    assert all(p.endswith(".jsonl") for p in rec["corpus"]["drilled"])
    assert rec["schema"] == "canopy.origin/v1"


def test_render_context_flags_local_availability(tmp_path):
    present = tmp_path / "s1.jsonl"; present.write_text("{}")
    rec = _rec(tmp_path)
    ctx = io.render_context(rec)
    assert "canopy harvest strip" in ctx
    assert "✓ local" in ctx           # the existing session
    assert "NOT on this machine" in ctx  # the missing one
    assert "harvest map ddd --full" in ctx


def test_web_sync_is_best_effort(tmp_path):
    ok, msg = io.web_sync(_rec(tmp_path))   # no canopy-web endpoint in test → must not raise
    assert ok in (True, False) and isinstance(msg, str)


def test_web_payload_drops_envelope_fields(tmp_path):
    rec = _rec(tmp_path)
    payload = io._web_payload(rec)
    assert "schema" not in payload and "issue" not in payload   # envelope fields excluded
    assert payload["repo"] == "jjackson/canopy" and payload["number"] == 42
    assert payload["corpus"]["drilled"]                          # pointers carried through


def test_delete_local(tmp_path, monkeypatch):
    monkeypatch.setattr(io, "_store_dir", lambda: tmp_path / "issues")
    io.save_local(_rec(tmp_path))
    assert io.delete_local("jjackson/canopy", 42) is True
    assert io.load_local("jjackson/canopy", 42) is None
    assert io.delete_local("jjackson/canopy", 42) is False       # already gone
