"""Tests for fleet_align — cross-agent improvement spread.

The deterministic core is pure/offline: we stamp fixture agent repos that diverge in KNOWN ways
and assert the exact findings/kinds. No network, no LLM, no git required.
"""
from __future__ import annotations

import json

import pytest

from orchestrator import fleet_align as fa


# A tiny factory-template baseline (marker sets), independent of the real agent_factory strings so
# the tests pin behaviour, not the live templates.
TEMPLATE_SELF_REVIEW = """---
name: self-review
---
# Self-review
1. **Re-read the original request.** actual message.
2. **Extract each discrete ask.**
3. **For each ask, confirm the draft does exactly that.**
4. **Deliverables are gdocs; the draft is inline.**
5. **Verify recipients.**
"""

BASELINE = {
    "agent-turn-review": fa.extract_skill_markers(TEMPLATE_SELF_REVIEW, []),
    "turn": set(),
    "gating": {"deny": {"BLOCK_RAW_SEND"}, "approve_count": 0},
}


def _write_agent(root, slug, *, self_review=None, gating=None, turn="# Turn\n## Step 1 — preflight\n", agent_json=True):
    d = root / slug
    (d / "skills" / "turn").mkdir(parents=True)
    (d / "skills" / "turn" / "SKILL.md").write_text(turn)
    if self_review is not None:
        (d / "skills" / "agent-turn-review").mkdir(parents=True)
        (d / "skills" / "agent-turn-review" / "SKILL.md").write_text(self_review)
    if gating is not None:
        (d / "config").mkdir(parents=True, exist_ok=True)
        (d / "config" / "gating.json").write_text(json.dumps(gating))
    if agent_json:
        (d / "config").mkdir(parents=True, exist_ok=True)
        (d / "config" / "agent.json").write_text(json.dumps({"name": slug.capitalize()}))
    return d


def test_discovery_marker_is_turn_skill_not_agent_json(tmp_path):
    # An agent WITHOUT agent.json (legacy, like echo) is still discovered via the turn skill.
    _write_agent(tmp_path, "legacy", agent_json=False)
    # A repo with no turn skill is NOT an agent.
    (tmp_path / "notanagent").mkdir()
    (tmp_path / "notanagent" / "README.md").write_text("hi")

    agents = fa.discover_agents(bases=[tmp_path])
    slugs = {a.slug for a in agents}
    assert slugs == {"legacy"}
    assert agents[0].factory_marked is False


def test_stale_agents_grouped_into_one_distribute_finding(tmp_path):
    # Two agents missing the SAME two template steps → one grouped DISTRIBUTE-from-template finding.
    stale = TEMPLATE_SELF_REVIEW.rsplit("4.", 1)[0]  # drop steps 4 & 5
    _write_agent(tmp_path, "eva", self_review=stale, gating={"deny": [{"pattern": "BLOCK_RAW_SEND"}], "approve": []})
    _write_agent(tmp_path, "hal", self_review=stale, gating={"deny": [{"pattern": "BLOCK_RAW_SEND"}], "approve": []})

    agents = fa.discover_agents(bases=[tmp_path])
    findings = fa.analyze(agents, baseline=BASELINE)

    sr = [f for f in findings if f.artifact == "agent-turn-review"]
    assert len(sr) == 1
    f = sr[0]
    assert f.kind == "distribute"
    assert f.reference == "canopy-template"
    assert sorted(f.laggards) == ["eva", "hal"]
    assert any("verify recipients" in d for d in f.detail)


def test_deprecated_approve_rules_flagged(tmp_path):
    _write_agent(tmp_path, "eva", self_review=TEMPLATE_SELF_REVIEW,
                 gating={"deny": [{"pattern": "BLOCK_RAW_SEND"}], "approve": [{"pattern": "git push"}]})
    agents = fa.discover_agents(bases=[tmp_path])
    findings = fa.analyze(agents, baseline=BASELINE)

    approve = [f for f in findings if f.artifact == "gating" and "approve" in f.summary]
    assert len(approve) == 1
    assert approve[0].kind == "distribute"
    assert approve[0].laggards == ["eva"]


def test_convergent_extra_step_is_promoted(tmp_path):
    # Two agents INDEPENDENTLY added the same step the template lacks → PROMOTE (strongest signal).
    plus = TEMPLATE_SELF_REVIEW + "6. **Rate it, tough — score 1 to 5.**\n"
    _write_agent(tmp_path, "eva", self_review=plus, gating={"deny": [{"pattern": "BLOCK_RAW_SEND"}], "approve": []})
    _write_agent(tmp_path, "hal", self_review=plus, gating={"deny": [{"pattern": "BLOCK_RAW_SEND"}], "approve": []})

    agents = fa.discover_agents(bases=[tmp_path])
    findings = fa.analyze(agents, baseline=BASELINE)

    promote = [f for f in findings if f.kind == "promote"]
    assert len(promote) == 1
    assert promote[0].laggards == ["canopy-template"]
    assert "rate it" in promote[0].detail[0]
    # promote sorts first
    assert findings[0].kind == "promote"


def test_identity_tokens_are_normalized_out(tmp_path):
    # The agent's own name appearing in a step must NOT read as a divergence from the template.
    tmpl = "# Self-review\n1. **Reply as <agent> to the request.**\n"
    baseline = {"agent-turn-review": fa.extract_skill_markers(tmpl, []), "turn": set(), "gating": {"deny": set(), "approve_count": 0}}
    _write_agent(tmp_path, "eva", self_review="# Self-review\n1. **Reply as Eva to the request.**\n",
                 gating={"deny": [], "approve": []})
    agents = fa.discover_agents(bases=[tmp_path])
    findings = fa.analyze(agents, baseline=baseline)
    assert [f for f in findings if f.artifact == "agent-turn-review"] == []


def test_divergent_lineage_flagged_not_itemized_as_stale(tmp_path):
    # An agent structurally unlike the template (low overlap) → reconcile, not a noisy stale finding.
    weird = "# Self-review\n1. **Totally different step A.**\n2. **Unrelated step B.**\n3. **Novel step C.**\n"
    _write_agent(tmp_path, "echo", self_review=weird, gating={"deny": [], "approve": []}, agent_json=False)
    agents = fa.discover_agents(bases=[tmp_path])
    findings = fa.analyze(agents, baseline=BASELINE)
    sr = [f for f in findings if f.artifact == "agent-turn-review"]
    assert len(sr) == 1
    assert sr[0].kind == "reconcile"
    assert sr[0].reference == "echo"


def test_no_findings_when_fleet_matches_template(tmp_path):
    _write_agent(tmp_path, "eva", self_review=TEMPLATE_SELF_REVIEW, gating={"deny": [{"pattern": "BLOCK_RAW_SEND"}], "approve": []})
    agents = fa.discover_agents(bases=[tmp_path])
    findings = fa.analyze(agents, baseline=BASELINE)
    assert [f for f in findings if f.artifact == "agent-turn-review"] == []
    assert "aligned" in fa.format_report(agents, [])


def test_legacy_agent_is_never_a_stale_laggard(tmp_path):
    # echo (no agent.json) missing template steps must be RECONCILE (ancestor), never distribute.
    stale = TEMPLATE_SELF_REVIEW.rsplit("4.", 1)[0]
    _write_agent(tmp_path, "echo", self_review=stale, gating={"deny": [], "approve": []}, agent_json=False)
    agents = fa.discover_agents(bases=[tmp_path])
    findings = fa.analyze(agents, baseline=BASELINE)
    sr = [f for f in findings if f.artifact == "agent-turn-review"]
    assert sr and all(f.kind != "distribute" for f in sr)
    assert sr[0].kind == "reconcile"


# ── evidence ──────────────────────────────────────────────────────────────────

def test_probe_selection_matches_known_findings():
    recip = fa.Finding("distribute", "agent-turn-review", "canopy-template", ["eva"], "…", detail=["verify recipients"])
    assert fa._probe_for(recip) is not None
    none = fa.Finding("distribute", "gating", "canopy-template", ["eva"], "deprecated approve rules", detail=["eva: 3 approve rule(s)"])
    assert fa._probe_for(none) is None  # no probe for the approve-cleanup finding → honest zero


def test_gather_evidence_attaches_matching_sessions(tmp_path, monkeypatch):
    _write_agent(tmp_path, "eva", self_review=TEMPLATE_SELF_REVIEW, gating={"deny": [], "approve": []})
    agents = fa.discover_agents(bases=[tmp_path])
    finding = fa.Finding("distribute", "agent-turn-review", "canopy-template", ["eva"], "…", detail=["verify recipients"])

    fake = tmp_path / "sess.jsonl"
    fake.write_text("{}")
    from orchestrator import agent_review
    monkeypatch.setattr(agent_review, "find_turn_transcripts", lambda repo, hours, projects_dir: [fake])
    monkeypatch.setattr(fa, "_turn_corpus", lambda p: "we sent it reply-all, To: Andrea Cc: Jonathan")

    fa.gather_evidence([finding], agents, hours=100)
    assert len(finding.evidence) == 1
    assert finding.evidence[0].agent == "eva"
    assert "recipient" in finding.evidence[0].signal


def test_evidence_search_spans_all_logins(tmp_path, monkeypatch):
    # eva's turns live under a DIFFERENT login — the search must find them cross-user.
    _write_agent(tmp_path, "eva", self_review=TEMPLATE_SELF_REVIEW, gating={"deny": [], "approve": []})
    agents = fa.discover_agents(bases=[tmp_path])
    finding = fa.Finding("distribute", "agent-turn-review", "canopy-template", ["eva"], "…", detail=["verify recipients"])

    login_a = tmp_path / "Users" / "acedimagi" / ".claude" / "projects"
    login_b = tmp_path / "Users" / "jjackson" / ".claude" / "projects"
    login_a.mkdir(parents=True)
    login_b.mkdir(parents=True)
    sess_b = login_b / "eva-sess.jsonl"
    sess_b.write_text("{}")

    monkeypatch.setattr(fa, "claude_projects_roots", lambda: ([login_a, login_b], 0))
    from orchestrator import agent_review
    # only the jjackson root has eva's transcript
    monkeypatch.setattr(agent_review, "find_turn_transcripts",
                        lambda repo, hours, projects_dir: [sess_b] if projects_dir == login_b else [])
    monkeypatch.setattr(fa, "_turn_corpus", lambda p: "verify recipients — we cc'd the wrong person")

    fa.gather_evidence([finding], agents, hours=100)
    assert len(finding.evidence) == 1
    assert finding.evidence[0].session_id == "eva-sess"


def test_promote_gathers_source_side_positive_evidence(tmp_path, monkeypatch):
    # A PROMOTE (or reconcile) referencing echo → search ECHO's sessions for the pattern in USE.
    _write_agent(tmp_path, "echo", self_review="# sr\n1. **Rate it, tough.**\n", agent_json=False)
    agents = fa.discover_agents(bases=[tmp_path])
    f = fa.Finding("promote", "agent-turn-review", "echo", ["canopy-template"], "…", detail=["rate it, tough"])

    sess = tmp_path / "echo-sess.jsonl"
    sess.write_text("{}")
    from orchestrator import agent_review
    monkeypatch.setattr(agent_review, "find_turn_transcripts", lambda repo, hours, projects_dir: [sess])
    monkeypatch.setattr(fa, "_turn_corpus", lambda p: "ran the self-review skill: rated faithfulness 3/5, fixed the gap before sending")

    fa.gather_evidence([f], agents, hours=100, projects_dir=tmp_path)
    assert len(f.evidence) == 1
    assert f.evidence[0].agent == "echo"
    assert "turn-review discipline" in f.evidence[0].signal


def test_reconcile_with_no_source_probe_gets_no_evidence(tmp_path, monkeypatch):
    # gating has no source probe → a reconcile gating finding gathers nothing (honest zero).
    f = fa.Finding("reconcile", "gating", "hal", [], "…", detail=["some rule"])
    from orchestrator import agent_review
    monkeypatch.setattr(agent_review, "find_turn_transcripts", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not search")))
    fa.gather_evidence([f], [], hours=100, projects_dir=tmp_path)
    assert f.evidence == []


def test_evidence_rank_floats_backed_findings_up():
    a = fa.Finding("distribute", "gating", "canopy-template", ["eva"], "no evidence")
    b = fa.Finding("distribute", "agent-turn-review", "canopy-template", ["eva"], "backed")
    b.evidence = [fa.Evidence("eva", "s1", "2026-07-01", "recipient / cc handling", "…")]
    assert fa.evidence_rank([a, b])[0] is b


# ── judgment ──────────────────────────────────────────────────────────────────

def test_judge_applies_verdict_and_drops(monkeypatch):
    findings = [
        fa.Finding("distribute", "agent-turn-review", "canopy-template", ["eva"], "keep me"),
        fa.Finding("distribute", "gating", "canopy-template", ["eva"], "drop me"),
    ]
    verdict = json.dumps([
        {"index": 0, "final_kind": "distribute", "direction_ok": True, "rationale": "real, evidence-backed", "action": "backport"},
        {"index": 1, "final_kind": "drop", "direction_ok": True, "rationale": "not applicable", "action": ""},
    ])
    kept = fa.judge(findings, runner=lambda prompt, model: verdict)
    assert len(kept) == 1
    assert kept[0].summary == "keep me"
    assert kept[0].rationale == "real, evidence-backed"
    assert kept[0].action == "backport"


def test_judge_survives_bad_llm_output(monkeypatch):
    findings = [fa.Finding("distribute", "agent-turn-review", "canopy-template", ["eva"], "x")]
    assert fa.judge(findings, runner=lambda p, m: "not json") == findings  # deterministic findings stand


# ── change brief (the AI apply agent's spec — NOT a mechanical patch) ─────────

def test_change_brief_gives_reference_text_not_a_mutation(monkeypatch):
    # The brief hands the AI the template's exact text for the MISSING steps — no file mutation here.
    tmpl = ("# Self-review\n"
            "1. **Re-read the original request.** actual message.\n"
            "2. **Verify recipients.** pull to/cc from the structured reader, not a raw view.\n")
    monkeypatch.setattr(fa.agent_factory, "_AGENT_TURN_REVIEW_SKILL", tmpl)
    d = fa.Finding("distribute", "agent-turn-review", "canopy-template", ["eva"], "…", detail=["verify recipients"])
    brief = fa.change_brief(d)
    assert brief["target_relpath"].endswith("agent-turn-review/SKILL.md")
    assert "old" not in brief and "new" not in brief         # never a computed file edit
    assert len(brief["add_reference"]) == 1 and "Verify recipients" in brief["add_reference"][0]
    assert "Re-read the original request" not in brief["add_reference"][0]  # only the MISSING step
    assert "do NOT regenerate" in brief["instruction"]


def test_change_brief_gating_approve_gives_remove_hint_and_applicability_instruction():
    approve = fa.Finding("distribute", "gating", "canopy-template", ["eva"],
                         "gating: still carry deprecated `approve` rules", detail=["eva: 3 approve rule(s)"])
    b1 = fa.change_brief(approve)
    assert b1["remove_hint"] and "approve" in b1["remove_hint"]
    deny = fa.Finding("distribute", "gating", "canopy-template", ["eva"],
                      "gating: missing template deny rail(s)", detail=["gog gmail send"])
    b2 = fa.change_brief(deny)
    assert "ONLY IF" in b2["instruction"]                    # applicability + placeholder-substitution is the AI's job
    assert "{{AGENT" in b2["instruction"] or "placeholder" in b2["instruction"].lower()


def test_change_brief_none_for_promote_and_reconcile():
    assert fa.change_brief(fa.Finding("promote", "agent-turn-review", "echo", ["canopy-template"], "…")) is None
    assert fa.change_brief(fa.Finding("reconcile", "turn", "hal", [], "…")) is None
