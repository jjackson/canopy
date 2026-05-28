"""Tests for scripts/ddd/narrative.py — narrative-agreement gate.

All functions under test are pure (no network, no disk-for-build, only
disk-for-apply).  The CLI's network-touching 'post' path is not tested here.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from scripts.ddd.schemas.models import Decision, Persona, ReviewRequest, Scene, UnifiedSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(scenes: list[Scene] | None = None) -> UnifiedSpec:
    if scenes is None:
        scenes = [
            Scene(
                persona="alice",
                title="Area Selection",
                show="Navigate to /areas and draw a boundary on the map.",
                concept_claim="Users can draw a custom boundary to select the survey area within 30 seconds.",
                provenance="S1",
            ),
            Scene(
                persona="alice",
                title="Sample Generation",
                show="Click 'Generate Sample' and review the building list.",
                concept_claim="The system generates a proportional building sample and displays it on the map.",
                provenance="S2",
            ),
            Scene(
                persona="bob",
                title="Field Assignment",
                show="Assign buildings to field workers from the team dashboard.",
                concept_claim="Supervisors can assign sampled buildings to field workers with a single tap.",
                provenance="S3",
            ),
        ]
    return UnifiedSpec(
        name="rooftop-surveys",
        narrative="Rooftop surveys ride Connect microplanning.",
        base_url="https://labs.connect.dimagi.com",
        personas={
            "alice": Persona(
                name="Alice",
                role="Program Manager",
                color="#3B82F6",
                intro="Alice manages rooftop survey programs.",
            ),
            "bob": Persona(
                name="Bob",
                role="Field Supervisor",
                color="#10B981",
                intro="Bob assigns work to field teams.",
            ),
        },
        scenes=scenes,
    )


def _write_spec(tmp_path: Path, spec: UnifiedSpec) -> Path:
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        yaml.dump(spec.model_dump(), default_flow_style=False, allow_unicode=True)
    )
    return spec_path


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------


from scripts.ddd.narrative import apply_narrative_edits, build_narrative_review_request


# ---------------------------------------------------------------------------
# build_narrative_review_request — pure function tests
# ---------------------------------------------------------------------------


class TestBuildNarrativeReviewRequest:
    def test_returns_review_request_instance(self):
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        assert isinstance(result, ReviewRequest)

    def test_gate_is_concept_change(self):
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        assert result.gate == "concept_change"

    def test_run_id_preserved(self):
        spec = _make_spec()
        result = build_narrative_review_request(spec, "my-run-42")
        assert result.run_id == "my-run-42"

    def test_video_is_empty_dict(self):
        """No cut yet — this is a pre-render narrative review."""
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        assert result.video == {}

    def test_autonomous_audit_is_empty(self):
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        assert result.autonomous_audit == []

    def test_narration_has_one_item_per_scene(self):
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        assert len(result.narration) == len(spec.scenes)

    def test_narration_items_have_required_keys(self):
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        for item in result.narration:
            assert "scene" in item, f"narration item missing 'scene' key: {item}"
            assert "id" in item, f"narration item missing 'id' key: {item}"
            assert "text" in item, f"narration item missing 'text' key: {item}"

    def test_narration_scene_indices_are_zero_based(self):
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        for i, item in enumerate(result.narration):
            assert item["scene"] == i, (
                f"scene index mismatch at position {i}: expected {i}, got {item['scene']}"
            )

    def test_narration_text_is_concept_claim(self):
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        for item, scene in zip(result.narration, spec.scenes):
            assert item["text"] == scene.concept_claim, (
                f"narration item text must be the scene's concept_claim; "
                f"got {item['text']!r}, expected {scene.concept_claim!r}"
            )

    def test_narration_id_is_title_slug(self):
        """id must be the scene title lowercased with spaces replaced by hyphens."""
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        for item, scene in zip(result.narration, spec.scenes):
            expected_slug = re.sub(r"[^a-z0-9]+", "-", scene.title.lower()).strip("-")
            assert item["id"] == expected_slug, (
                f"narration item id must be a slug of the scene title; "
                f"got {item['id']!r}, expected {expected_slug!r}"
            )

    def test_decisions_contains_one_narrative_verdict(self):
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        assert len(result.decisions) == 1
        decision = result.decisions[0]
        assert decision.id == "narrative-verdict"

    def test_decision_prompt_is_narrative_focused(self):
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        decision = result.decisions[0]
        # Must mention both narrative agreement and building/rendering
        assert "narrative" in decision.prompt.lower() or "story" in decision.prompt.lower()

    def test_decision_options_are_agree_edit_rethink(self):
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        decision = result.decisions[0]
        assert set(decision.options) == {"agree", "edit", "rethink"}, (
            f"decision options must be {{agree, edit, rethink}}; got {decision.options}"
        )

    def test_decision_recommended_is_agree(self):
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        decision = result.decisions[0]
        assert decision.recommended == "agree"

    def test_decision_class_is_concept_change(self):
        """Decision must use class_='concept_change' (stored under alias 'class')."""
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        decision = result.decisions[0]
        assert decision.class_ == "concept_change"

    def test_decision_model_dump_emits_class_alias(self):
        """model_dump(by_alias=True) must emit 'class', not 'class_'."""
        spec = _make_spec()
        result = build_narrative_review_request(spec, "run-001")
        decision = result.decisions[0]
        dumped = decision.model_dump(by_alias=True)
        assert "class" in dumped, f"alias 'class' not in dump; keys: {list(dumped)}"
        assert "class_" not in dumped, f"raw field 'class_' leaked into dump: {dumped}"
        assert dumped["class"] == "concept_change"

    def test_single_scene_spec(self):
        """Works correctly with a single scene."""
        spec = _make_spec(
            scenes=[
                Scene(
                    persona="alice",
                    title="Only Scene",
                    show="Navigate to home.",
                    concept_claim="Users can see the dashboard summary on first load.",
                    provenance="S1",
                )
            ]
        )
        result = build_narrative_review_request(spec, "run-single")
        assert len(result.narration) == 1
        assert result.narration[0]["scene"] == 0
        assert result.narration[0]["text"] == "Users can see the dashboard summary on first load."


# ---------------------------------------------------------------------------
# apply_narrative_edits — disk-touching pure transform
# ---------------------------------------------------------------------------


class TestApplyNarrativeEdits:
    def test_returns_dict_with_decision_and_edited(self, tmp_path):
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)
        response = {
            "decisions": {"narrative-verdict": "agree"},
            "narration_edits": {},
        }
        result = apply_narrative_edits(str(spec_path), response)
        assert "decision" in result
        assert "edited" in result

    def test_agree_decision_round_trips(self, tmp_path):
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)
        response = {
            "decisions": {"narrative-verdict": "agree"},
            "narration_edits": {},
        }
        result = apply_narrative_edits(str(spec_path), response)
        assert result["decision"] == "agree"

    def test_edit_decision_round_trips(self, tmp_path):
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)
        response = {
            "decisions": {"narrative-verdict": "edit"},
            "narration_edits": {},
        }
        result = apply_narrative_edits(str(spec_path), response)
        assert result["decision"] == "edit"

    def test_rethink_decision_round_trips(self, tmp_path):
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)
        response = {
            "decisions": {"narrative-verdict": "rethink"},
            "narration_edits": {},
        }
        result = apply_narrative_edits(str(spec_path), response)
        assert result["decision"] == "rethink"

    def test_no_edits_returns_zero_edited_count(self, tmp_path):
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)
        response = {
            "decisions": {"narrative-verdict": "agree"},
            "narration_edits": {},
        }
        result = apply_narrative_edits(str(spec_path), response)
        assert result["edited"] == 0

    def test_applies_narration_edit_to_concept_claim(self, tmp_path):
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)

        # Build the slug for scene 0 ("Area Selection")
        scene0_slug = re.sub(r"[^a-z0-9]+", "-", "Area Selection".lower()).strip("-")
        new_claim = "Users draw a precise boundary in under 30 seconds using satellite imagery."

        response = {
            "decisions": {"narrative-verdict": "edit"},
            "narration_edits": {scene0_slug: new_claim},
        }
        apply_narrative_edits(str(spec_path), response)

        # Reload and verify
        updated = yaml.safe_load(spec_path.read_text())
        assert updated["scenes"][0]["concept_claim"] == new_claim

    def test_applies_edit_to_correct_scene_by_slug(self, tmp_path):
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)

        # Edit scene 2 ("Field Assignment") only
        scene2_slug = re.sub(r"[^a-z0-9]+", "-", "Field Assignment".lower()).strip("-")
        new_claim = "Supervisors assign buildings to FLWs with drag-and-drop, confirmed in one tap."

        response = {
            "decisions": {"narrative-verdict": "edit"},
            "narration_edits": {scene2_slug: new_claim},
        }
        apply_narrative_edits(str(spec_path), response)

        updated = yaml.safe_load(spec_path.read_text())
        # Scene 0 and 1 unchanged
        assert updated["scenes"][0]["concept_claim"] == spec.scenes[0].concept_claim
        assert updated["scenes"][1]["concept_claim"] == spec.scenes[1].concept_claim
        # Scene 2 updated
        assert updated["scenes"][2]["concept_claim"] == new_claim

    def test_edited_count_matches_changed_scenes(self, tmp_path):
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)

        scene0_slug = re.sub(r"[^a-z0-9]+", "-", "Area Selection".lower()).strip("-")
        scene1_slug = re.sub(r"[^a-z0-9]+", "-", "Sample Generation".lower()).strip("-")

        response = {
            "decisions": {"narrative-verdict": "edit"},
            "narration_edits": {
                scene0_slug: "New claim for scene 0.",
                scene1_slug: "New claim for scene 1.",
            },
        }
        result = apply_narrative_edits(str(spec_path), response)
        assert result["edited"] == 2

    def test_unmatched_narration_id_is_silently_skipped(self, tmp_path):
        """Unknown keys in narration_edits must not raise errors."""
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)

        response = {
            "decisions": {"narrative-verdict": "agree"},
            "narration_edits": {
                "this-slug-does-not-exist": "Some text that should be ignored.",
                "another-bogus-slug": "More ignored text.",
            },
        }
        # Must NOT raise
        result = apply_narrative_edits(str(spec_path), response)
        assert result["edited"] == 0

        # Spec on disk must be unchanged
        updated = yaml.safe_load(spec_path.read_text())
        for i, scene in enumerate(spec.scenes):
            assert updated["scenes"][i]["concept_claim"] == scene.concept_claim

    def test_accepts_path_object(self, tmp_path):
        """apply_narrative_edits accepts a pathlib.Path, not only str."""
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)

        response = {"decisions": {"narrative-verdict": "agree"}, "narration_edits": {}}
        # Must not raise
        result = apply_narrative_edits(spec_path, response)
        assert result["decision"] == "agree"

    def test_missing_decisions_key_defaults_to_agree(self, tmp_path):
        """Robust default: if 'decisions' key absent, decision defaults to 'agree'."""
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)
        response = {"narration_edits": {}}
        result = apply_narrative_edits(str(spec_path), response)
        assert result["decision"] == "agree"

    def test_missing_narration_edits_key_is_handled(self, tmp_path):
        """Robust default: if 'narration_edits' absent, no changes are applied."""
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)
        response = {"decisions": {"narrative-verdict": "rethink"}}
        result = apply_narrative_edits(str(spec_path), response)
        assert result["edited"] == 0
        assert result["decision"] == "rethink"

    def test_writes_spec_back_to_disk(self, tmp_path):
        """After apply, spec file on disk must be valid YAML with updated content."""
        spec = _make_spec()
        spec_path = _write_spec(tmp_path, spec)

        scene0_slug = re.sub(r"[^a-z0-9]+", "-", "Area Selection".lower()).strip("-")
        response = {
            "decisions": {"narrative-verdict": "edit"},
            "narration_edits": {scene0_slug: "Updated claim."},
        }
        apply_narrative_edits(str(spec_path), response)

        # Must still be valid YAML
        updated = yaml.safe_load(spec_path.read_text())
        assert isinstance(updated, dict)
        assert "scenes" in updated
