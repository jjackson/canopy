"""Tests for scripts/ddd/findings_review.py (product-findings review gate).

All HTTP calls are mocked — no real network traffic.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.ddd.findings_review import (
    GATE,
    OVERALL_DECISION_ID,
    _clip_content_url,
    _format_ts,
    build_findings_review_request,
    cluster_findings,
    evidence_links,
    make_scene_resolver,
    parse_selection,
    resolve_review_mode,
)
from scripts.ddd.schemas.models import ReviewRequest

DECK = "https://canopy-web.example/w/11111111-1111-1111-1111-111111111111?t=decktok"
CLIP = "https://canopy-web.example/w/22222222-2222-2222-2222-222222222222?t=cliptok"


def _finding(scene=2, dimension="visual_polish", severity="medium", detail="The hero chart is illegibly small.",
             fix="Make the chart the page hero.", fix_kind="mechanical", route="PRODUCT", **extra):
    f = {
        "scene": scene,
        "dimension": dimension,
        "severity": severity,
        "route": route,
        "detail": detail,
        "fix_recommendation": fix,
        "fix_kind": fix_kind,
    }
    f.update(extra)
    return f


SPEC = {
    "name": "verified-monitoring",
    "narrative": "x",
    "base_url": "https://labs.example",
    "personas": {},
    "scenes": [
        {"title": "Area Selection"},
        {"title": "Field Assignment"},
        {"title": "Review Dashboard"},
    ],
}


# ---------------------------------------------------------------------------
# Scene resolution
# ---------------------------------------------------------------------------


def test_scene_resolver_handles_int_digit_title_and_scene_n():
    resolve = make_scene_resolver(SPEC)
    assert resolve(2) == 2
    assert resolve("3") == 3
    assert resolve("Field Assignment") == 2
    assert resolve("Scene 3") == 3
    assert resolve("Unknown Title") is None
    assert resolve(None) is None
    assert resolve("") is None


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


def test_clusters_dedupe_by_scene_and_dimension():
    findings = [
        _finding(scene=2, dimension="visual_polish", detail="Chart too small."),
        _finding(scene=2, dimension="visual_polish", detail="Legend unreadable.", severity="high",
                 fix="Bigger legend.", fix_kind="options"),
        _finding(scene=3, dimension="visual_polish", detail="Table cramped."),
    ]
    clusters = cluster_findings(findings, scene_resolver=make_scene_resolver(SPEC))
    assert len(clusters) == 2
    merged = clusters[0]
    assert merged["cluster_id"] == "scene-2-visual-polish"
    assert merged["count"] == 2
    assert merged["scenes"] == [2]
    # Worst-of merges: severity high beats medium, options beats mechanical.
    assert merged["severity"] == "high"
    assert merged["fix_kind"] == "options"
    assert "Chart too small." in merged["detail"] and "Legend unreadable." in merged["detail"]
    assert "Bigger legend." in merged["suggested_fix"]


def test_explicit_cluster_key_groups_across_scenes():
    findings = [
        _finding(scene=1, cluster="picker UX"),
        _finding(scene=3, dimension="clarity", cluster="picker UX"),
    ]
    clusters = cluster_findings(findings, scene_resolver=make_scene_resolver(SPEC))
    assert len(clusters) == 1
    assert clusters[0]["cluster_id"] == "picker-ux"
    assert clusters[0]["scenes"] == [1, 3]


def test_non_product_routes_are_excluded():
    findings = [
        _finding(route="CONCEPT"),
        _finding(route="RESEARCH"),
        _finding(route="DEFER"),
        _finding(route="PRODUCT", scene=1),
    ]
    clusters = cluster_findings(findings, scene_resolver=make_scene_resolver(SPEC))
    assert len(clusters) == 1
    assert clusters[0]["scenes"] == [1]


def test_user_verdict_dimensions_become_clusters():
    user_verdict = {
        "dimensions": {
            "task_completion": {
                "score": 2,
                "weight": 0.4,
                "justification": "Ambiguous rows offer only Skip.",
                "fix_recommendation": "Add an inline picker per row.",
                "fix_kind": "mechanical",
            },
            "clarity": {"score": 5, "weight": 0.35, "justification": "fine"},
        }
    }
    clusters = cluster_findings([], user_verdict=user_verdict)
    assert len(clusters) == 1
    c = clusters[0]
    assert c["cluster_id"] == "user-task-completion"
    assert c["severity"] == "high"  # score <= 2
    assert c["fix_kind"] == "mechanical"
    assert c["scenes"] == []
    assert "inline picker" in c["suggested_fix"]


def test_title_resolved_scene_strings_cluster_with_indices():
    findings = [
        _finding(scene="Field Assignment", detail="Label confusing."),
        _finding(scene=2, detail="CTA hidden."),
    ]
    clusters = cluster_findings(findings, scene_resolver=make_scene_resolver(SPEC))
    assert len(clusters) == 1
    assert clusters[0]["scenes"] == [2]


# ---------------------------------------------------------------------------
# Evidence links
# ---------------------------------------------------------------------------


def test_evidence_links_carry_scene_anchor_and_time_param():
    cluster = {"scenes": [2], "scene_labels": []}
    links = evidence_links(cluster, deck_url=DECK, clip_url=CLIP, scene_timestamps={2: 83.4})
    urls = [e["url"] for e in links]
    assert f"{DECK}#scene-2" in urls
    assert f"{CLIP}#t=83" in urls
    labels = [e["label"] for e in links]
    assert any("1:23" in label for label in labels)


def test_evidence_omits_video_link_for_untimed_scene():
    # Scene 4 was skipped by --skip-empty-scenes → no timestamp → deck only.
    cluster = {"scenes": [4], "scene_labels": []}
    links = evidence_links(cluster, deck_url=DECK, clip_url=CLIP, scene_timestamps={2: 10.0})
    assert [e["url"] for e in links] == [f"{DECK}#scene-4"]


def test_sceneless_cluster_gets_bare_artifact_links():
    cluster = {"scenes": [], "scene_labels": []}
    links = evidence_links(cluster, deck_url=DECK, clip_url=CLIP, scene_timestamps={})
    assert [e["url"] for e in links] == [DECK, CLIP]


def test_format_ts():
    assert _format_ts(0) == "0:00"
    assert _format_ts(83.9) == "1:23"
    assert _format_ts(615) == "10:15"


def test_clip_content_url_derivation():
    assert (
        _clip_content_url(CLIP)
        == "https://canopy-web.example/w/22222222-2222-2222-2222-222222222222/content?t=cliptok"
    )
    assert _clip_content_url("https://elsewhere.example/video.mp4") is None
    assert _clip_content_url(None) is None


# ---------------------------------------------------------------------------
# Request building
# ---------------------------------------------------------------------------


def _build_request() -> ReviewRequest:
    findings = [
        _finding(scene=2, dimension="visual_polish"),
        _finding(scene=3, dimension="clarity", detail="Jargon in the table header.",
                 fix="Rename the header.", fix_kind="options"),
    ]
    user_verdict = {
        "dimensions": {
            "trust": {
                "score": 3,
                "weight": 0.25,
                "justification": "Data freshness unclear.",
                "fix_recommendation": "Show a last-updated stamp.",
                "fix_kind": "mechanical",
            }
        }
    }
    return build_findings_review_request(
        "verified-monitoring-2026-06-12-001",
        SPEC,
        findings,
        user_verdict,
        DECK,
        CLIP,
        {2: 42.0, 3: 81.5},
    )


def test_request_shape_gate_and_slug():
    req = _build_request()
    assert req.gate == GATE
    assert req.narrative_slug == "verified-monitoring"
    assert len(req.findings) == 3
    # Embedded video points at the streamable content URL, not the page route.
    assert req.video["url"].endswith("/content?t=cliptok")


def test_request_links_contain_scene_anchor_and_time_param():
    req = _build_request()
    by_id = {c["cluster_id"]: c for c in req.findings}
    ev = by_id["scene-2-visual-polish"]["evidence"]
    assert any(e["url"] == f"{DECK}#scene-2" for e in ev)
    assert any(e["url"] == f"{CLIP}#t=42" for e in ev)
    ev3 = by_id["scene-3-clarity"]["evidence"]
    assert any(e["url"] == f"{CLIP}#t=81" for e in ev3)
    # Narration text carries the same links so any review surface shows them.
    narration_text = "\n".join(n.text for n in req.narration)
    assert f"{DECK}#scene-2" in narration_text
    assert f"{CLIP}#t=42" in narration_text


def test_request_decisions_one_per_cluster_plus_overall():
    req = _build_request()
    ids = [d.id for d in req.decisions]
    assert ids[-1] == OVERALL_DECISION_ID
    assert set(ids[:-1]) == {"scene-2-visual-polish", "scene-3-clarity", "user-trust"}
    for d in req.decisions[:-1]:
        assert d.options == ["implement", "skip", "defer"]
        assert d.recommended == "implement"
        assert d.class_ == GATE
    overall = req.decisions[-1]
    assert overall.options == ["proceed with selected", "discuss"]
    assert overall.recommended == "proceed with selected"


def test_request_serializes_decisions_with_class_alias():
    req = _build_request()
    payload = req.model_dump(by_alias=True)
    assert all("class" in d for d in payload["decisions"])


def test_no_product_findings_yields_empty_findings_list():
    req = build_findings_review_request(
        "x-2026-06-12-001", SPEC, [_finding(route="CONCEPT")], None, DECK, CLIP, {}
    )
    assert req.findings == []
    # Only the overall decision remains — caller checks findings before posting.
    assert [d.id for d in req.decisions] == [OVERALL_DECISION_ID]


# ---------------------------------------------------------------------------
# Selection parsing (apply)
# ---------------------------------------------------------------------------


def test_parse_selection_buckets_decisions():
    response = {
        "decisions": {
            "scene-2-visual-polish": "implement",
            "scene-3-clarity": "skip",
            "user-trust": "defer",
            "weird-one": "maybe?",
            OVERALL_DECISION_ID: "proceed with selected",
        }
    }
    sel = parse_selection(response)
    assert sel["overall"] == "proceed with selected"
    assert sel["implement"] == ["scene-2-visual-polish"]
    assert sel["skip"] == ["scene-3-clarity"]
    assert sel["defer"] == ["user-trust"]
    # Unknown decision values are preserved but never bucketed (no auto-apply).
    assert {"cluster_id": "weird-one", "decision": "maybe?"} in sel["selections"]
    assert "weird-one" not in sel["implement"] + sel["skip"] + sel["defer"]


def test_parse_selection_tolerates_empty_response():
    sel = parse_selection({})
    assert sel == {"overall": None, "selections": [], "implement": [], "skip": [], "defer": []}


# ---------------------------------------------------------------------------
# Review mode resolution
# ---------------------------------------------------------------------------


def test_review_mode_defaults_to_autonomous(tmp_path):
    assert resolve_review_mode({}) == "autonomous"
    assert resolve_review_mode({"review_mode": "bogus"}) == "autonomous"
    assert resolve_review_mode(tmp_path / "missing.yaml") == "autonomous"


def test_review_mode_human_from_spec_file(tmp_path):
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.dump({**SPEC, "review_mode": "human"}))
    assert resolve_review_mode(spec_path) == "human"
    assert resolve_review_mode({"review_mode": "human"}) == "human"


def test_review_mode_validates_on_unified_spec():
    from scripts.narrative.models import UnifiedSpec

    spec = UnifiedSpec.model_validate({**SPEC, "review_mode": "human", "scenes": []})
    assert resolve_review_mode(spec) == "human"
    default = UnifiedSpec.model_validate({**SPEC, "scenes": []})
    assert default.review_mode == "autonomous"


# ---------------------------------------------------------------------------
# CLI post — stamps run_state (mocked HTTP)
# ---------------------------------------------------------------------------


def _seed_run(tmp_path, monkeypatch, *, with_findings=True) -> tuple[Path, str]:
    """Create a judged run dir under a tmp ddd dir; returns (run_dir, run_id)."""
    ddd_dir = tmp_path / ".canopy" / "ddd"
    runs = ddd_dir / "runs"
    run_id = "verified-monitoring-2026-06-12-001"
    run_dir = runs / run_id
    run_dir.mkdir(parents=True)

    import scripts.ddd.runstate as rs

    monkeypatch.setattr(rs, "_resolve_ddd_dir", lambda: ddd_dir)

    state = {
        "schema_version": 1,
        "run_id": run_id,
        "narrative_slug": "verified-monitoring",
        "phase": "judged",
        "iteration": 1,
        "iteration_decks": {1: DECK},
        "iteration_clips": {1: CLIP},
    }
    (run_dir / "run_state.yaml").write_text(yaml.dump(state))

    findings = [_finding(scene=2)] if with_findings else []
    (run_dir / "design_findings.json").write_text(json.dumps(findings))
    (run_dir / "verdict-user.yaml").write_text(
        yaml.dump({"dimensions": {"clarity": {"score": 5, "weight": 0.35}}})
    )
    (run_dir / "run-report.json").write_text(
        json.dumps({"scenes": [{"scene_index": 2, "title": "S2", "start_seconds": 42.0,
                                "duration_seconds": 5.0}]})
    )
    return run_dir, run_id


def test_cli_post_stamps_run_state(tmp_path, monkeypatch, capsys):
    run_dir, run_id = _seed_run(tmp_path, monkeypatch)

    import scripts.ddd.review as rv
    from scripts.ddd import findings_review as fr

    posted: dict = {}

    def fake_post(request, **kwargs):
        posted["request"] = request
        return {
            "id": "rev-123",
            "url": "/review/rev-123/?t=sharetok",
            "share_token": "sharetok",
        }

    monkeypatch.setattr(rv, "post_review_request", fake_post)
    # Keep the spec resolution off the real repo's docs/walkthroughs.
    monkeypatch.setattr(fr, "_default_spec_path", lambda slug: None)

    fr.main(["post", run_id])

    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["posted"] is True
    assert out["id"] == "rev-123"
    assert out["clusters"] == 1
    assert out["internal_url"].endswith("/review/rev-123/")
    assert "t=sharetok" in out["share_url"]

    # The posted request carried the evidence deep-links.
    req = posted["request"]
    assert req.gate == GATE
    ev_urls = [e["url"] for e in req.findings[0]["evidence"]]
    assert f"{DECK}#scene-2" in ev_urls
    assert f"{CLIP}#t=42" in ev_urls

    # run_state stamped with the review id + tokenized URL.
    raw = yaml.safe_load((run_dir / "run_state.yaml").read_text())
    assert raw["findings_review_id"] == "rev-123"
    assert "t=sharetok" in raw["findings_review_url"]


def test_cli_post_no_product_findings_is_clean_noop(tmp_path, monkeypatch, capsys):
    run_dir, run_id = _seed_run(tmp_path, monkeypatch, with_findings=False)

    import scripts.ddd.review as rv
    from scripts.ddd import findings_review as fr

    def boom(*a, **k):  # pragma: no cover - must not be reached
        raise AssertionError("post_review_request must not be called")

    monkeypatch.setattr(rv, "post_review_request", boom)
    monkeypatch.setattr(fr, "_default_spec_path", lambda slug: None)

    fr.main(["post", run_id])

    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out == {
        "posted": False,
        "reason": "no PRODUCT findings to review",
        "run_id": run_id,
    }
    raw = yaml.safe_load((run_dir / "run_state.yaml").read_text())
    assert raw.get("findings_review_id") is None


def test_cli_apply_prints_selection(tmp_path, capsys):
    from scripts.ddd import findings_review as fr

    response = tmp_path / "response.json"
    response.write_text(
        json.dumps(
            {
                "decisions": {
                    "scene-2-visual-polish": "implement",
                    OVERALL_DECISION_ID: "proceed with selected",
                }
            }
        )
    )
    fr.main(["apply", str(response)])
    out = json.loads(capsys.readouterr().out.strip())
    assert out["implement"] == ["scene-2-visual-polish"]
    assert out["overall"] == "proceed with selected"


def test_cli_mode_prints_review_mode(tmp_path, capsys):
    from scripts.ddd import findings_review as fr

    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.dump({**SPEC, "review_mode": "human"}))
    fr.main(["mode", str(spec_path)])
    assert capsys.readouterr().out.strip() == "human"
