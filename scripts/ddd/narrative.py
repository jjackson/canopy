"""Narrative-agreement gate for demo-driven-development v3 (ddd-v3).

This module adds the missing narrative-agreement step to the DDD loop.
Before rendering, judging, or routing gaps, the user must explicitly AGREE
to the demo narrative — the story the demo tells to a prospective user.

Public API (pure functions — no network):
    build_narrative_review_request(spec, run_id) -> ReviewRequest
    apply_narrative_edits(spec_path, response_json) -> dict

CLI (touches network via review.post_review_request):
    python -m scripts.ddd.narrative post <spec_path> <run_id>
    python -m scripts.ddd.narrative apply <spec_path> <response_json_file>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from scripts.ddd.schemas.models import Decision, Feature, NarrationItem, ReviewRequest, UnifiedSpec


# ---------------------------------------------------------------------------
# Slug helper (shared by build and apply so slugs always agree)
# ---------------------------------------------------------------------------


def _title_slug(title: str) -> str:
    """Convert a scene title to a URL-safe slug for use as a narration item id.

    Examples:
        "Area Selection"  -> "area-selection"
        "Field Assignment" -> "field-assignment"
        "Sample Gen (v2)"  -> "sample-gen-v2"
    """
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


# ---------------------------------------------------------------------------
# Pure build function
# ---------------------------------------------------------------------------


def build_narrative_review_request(
    spec: UnifiedSpec,
    run_id: str,
    actionability: dict | None = None,
    why_brief: dict | None = None,
) -> ReviewRequest:
    """Build a ReviewRequest for the narrative-agreement gate (DDD v3).

    This is a pre-render review — no video cut has been made yet, so
    ``video`` is an empty dict.  The narration list presents one item per
    scene, each carrying the scene's ``concept_claim`` as the editable
    story beat AND the scene's declared ``features[]`` (concrete buildable
    units).  The single decision uses the v3 approve/redraft shape.

    Parameters
    ----------
    spec:
        The fully-parsed UnifiedSpec for the feature under review.
    run_id:
        The DDD run identifier (e.g. ``"rooftop-surveys-2026-01-01-001"``).
    actionability:
        Optional actionability block populated by the caller after
        ``ddd-narrative-actionability-eval`` has run.  If provided, it is
        set on the returned ReviewRequest so the human reviewer can see the
        actionability score alongside the narration.  Leave ``None`` (the
        default) when posting before the eval has run.

    Returns
    -------
    ReviewRequest
        A ReviewRequest with gate="concept_change" ready to post via
        ``review.post_review_request``.
    """
    narration = [
        NarrationItem(
            scene=i,
            id=_title_slug(scene.title),
            title=scene.title,
            persona=scene.persona,
            provenance=scene.provenance,
            text=scene.concept_claim,
            features=scene.features,
        )
        for i, scene in enumerate(spec.scenes, start=1)
    ]

    # build_order: use spec's explicit order when set, else default to scene order
    build_order: list[str] = (
        spec.build_order
        if spec.build_order
        else [_title_slug(scene.title) for scene in spec.scenes]
    )

    decision = Decision(
        id="narrative-verdict",
        prompt=(
            "Approve this narrative as the build plan, or send it back to re-draft?"
        ),
        options=["approve", "redraft"],
        recommended="approve",
        **{"class": "concept_change"},
    )

    return ReviewRequest(
        run_id=run_id,
        gate="concept_change",
        video={},
        narration=narration,
        narrative=spec.narrative,
        personas={k: p.model_dump() for k, p in spec.personas.items()},
        why_brief=why_brief or {},
        autonomous_audit=[],
        decisions=[decision],
        actionability=actionability,
        build_order=build_order,
    )


# ---------------------------------------------------------------------------
# Disk-touching apply function
# ---------------------------------------------------------------------------


def _generate_feature_id(description: str, existing_ids: set[str]) -> str:
    """Generate a stable id for a new feature from its description.

    Uses the same slug technique as ``_title_slug`` to produce a deterministic,
    human-readable id.  If the candidate collides with an existing id, appends
    a numeric suffix.
    """
    base = re.sub(r"[^a-z0-9]+", "-", description.lower()).strip("-")[:40]
    if not base:
        base = "feature"
    candidate = base
    n = 1
    while candidate in existing_ids:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


_PERSONA_FIELDS = ("name", "role", "intro", "org", "color")
_SPINE_FIELDS = ("claim", "rationale")
_GAP_FIELDS = ("detail", "proposed_action")


def _apply_persona_edits(raw: dict, response_json: dict) -> int:
    """Apply ``edited_personas`` onto ``raw['personas']`` in place.

    Payload shape: ``{"<key>": {"name": ..., "org": ..., "role": ..., "intro": ...}}``
    (partial — only changed fields). Unknown keys are ignored (the key is the
    persona's stable identity and is never created/renamed here). Returns the
    number of fields changed.
    """
    edited: dict = response_json.get("edited_personas") or {}
    if not edited:
        return 0
    personas: dict = raw.get("personas") or {}
    changed = 0
    for key, fields in edited.items():
        if key not in personas or not isinstance(fields, dict):
            continue
        for f in _PERSONA_FIELDS:
            if f in fields and personas[key].get(f) != fields[f]:
                personas[key][f] = fields[f]
                changed += 1
    if changed:
        raw["personas"] = personas
    return changed


def _apply_why_brief_edits(spec_path: Path, raw: dict, response_json: dict) -> int:
    """Apply ``edited_why_brief`` onto the why-brief file referenced by the spec.

    Payload shape::

        {"problem": "...",
         "spine": {"<id>": {"claim": "...", "rationale": "..."}},
         "gaps":  {"<id>": {"detail": "...", "proposed_action": "..."}}}

    Only prose fields are editable; ids/status/type/claim_ref are structural and
    left untouched. Writes the why-brief file back in place. Returns the number of
    fields changed (0 if no edits, no why_brief link, or the file is unreadable).
    """
    edited: dict = response_json.get("edited_why_brief") or {}
    wb_rel = raw.get("why_brief")
    if not edited or not wb_rel:
        return 0
    wb_path = (Path(spec_path).parent / wb_rel).resolve()
    try:
        wb = yaml.safe_load(wb_path.read_text())
    except Exception:
        return 0
    if not isinstance(wb, dict):
        return 0

    changed = 0
    if "problem" in edited and wb.get("problem") != edited["problem"]:
        wb["problem"] = edited["problem"]
        changed += 1

    spine_edits: dict = edited.get("spine") or {}
    for item in wb.get("spine") or []:
        e = spine_edits.get(item.get("id"))
        if not isinstance(e, dict):
            continue
        for f in _SPINE_FIELDS:
            if f in e and item.get(f) != e[f]:
                item[f] = e[f]
                changed += 1

    gap_edits: dict = edited.get("gaps") or {}
    for gap in wb.get("gaps") or []:
        e = gap_edits.get(gap.get("id"))
        if not isinstance(e, dict):
            continue
        for f in _GAP_FIELDS:
            if f in e and gap.get(f) != e[f]:
                gap[f] = e[f]
                changed += 1

    if changed:
        wb_path.write_text(yaml.dump(wb, default_flow_style=False, allow_unicode=True, sort_keys=False))
    return changed


def apply_narrative_edits(
    spec_path: str | Path,
    response_json: dict,
) -> dict:
    """Apply narration edits from a resolved review response back onto the spec.

    Loads the spec YAML, reconciles scenes and features against the payload,
    writes the spec back to disk, and returns a structured result dict.

    The function supports two payload shapes:

    **New shape** (``edited_scenes`` key present)::

        {
            "decisions": {"narrative-verdict": "approve" | "redraft"},
            "edited_scenes": [
                {
                    "id": "<slug or 'new-<n>'>",
                    "title": "...",
                    "narration": "...",
                    "deleted": false,
                    "features": [
                        {"id": "<id or 'new-<n>'>", "description": "...",
                         "verify": "...", "feedback": "<optional>"}
                    ],
                    "feedback": "<optional per-scene>"
                }
            ],
            "overall_feedback": "<optional>"
        }

    Scene reconciliation rules:

    - ``"deleted": true`` → remove the matching ``Scene`` by slug id.
    - ``"new-*"`` id → append a new ``Scene`` (empty ``provenance``,
      first persona key, ``concept_claim`` from ``narration``).
    - existing id → update the matching ``Scene``'s ``concept_claim`` and
      reconcile its ``features``: update matching features, add ``new-*``
      features with stable generated ids, remove features absent from payload.

    **Legacy shape** (``narration_edits`` key, no ``edited_scenes``)::

        {
            "decisions": {"narrative-verdict": "approve" | "redraft"},
            "narration_edits": {"<scene-slug>": "<new concept_claim>", ...}
        }

    Legacy v2 decision values are coerced:
    ``"agree"``/``"edit"`` → ``"approve"``; ``"rethink"`` → ``"redraft"``.

    Parameters
    ----------
    spec_path:
        Path to the unified spec YAML file.
    response_json:
        The ``response_json`` dict from the resolved review.

    Returns
    -------
    dict
        New shape::

            {
                "decision": "approve" | "redraft",
                "applied": {"updated": n, "added": n, "deleted": n, "features_changed": n},
                "needs_grounding": ["<new scene title>", ...],
                "feedback": [
                    {"scope": "feature" | "scene" | "overall", "ref": str, "text": str}
                ]
            }

        Legacy shape (``narration_edits`` path) also returns ``"edited"`` for
        backward compatibility::

            {"decision": ..., "applied": ..., "needs_grounding": ...,
             "feedback": ..., "edited": n}
    """
    spec_path = Path(spec_path)
    raw = yaml.safe_load(spec_path.read_text())

    decisions: dict[str, str] = response_json.get("decisions", {}) or {}
    raw_decision: str = decisions.get("narrative-verdict", "approve")

    # Normalise to v3 vocabulary: legacy "agree"/"edit" → "approve"; "rethink" → "redraft".
    _LEGACY_MAP = {
        "agree": "approve",
        "edit": "approve",
        "rethink": "redraft",
    }
    decision: str = _LEGACY_MAP.get(raw_decision, raw_decision)

    # Persona + why-brief edits are independent of the scene-edit shape; apply
    # both up front. Persona edits mutate `raw` (written with the spec below);
    # why-brief edits write their own file.
    personas_changed = _apply_persona_edits(raw, response_json)
    why_brief_changed = _apply_why_brief_edits(Path(spec_path), raw, response_json)

    scenes: list[dict] = raw.get("scenes", [])

    # ------------------------------------------------------------------
    # NEW shape: edited_scenes
    # ------------------------------------------------------------------
    if "edited_scenes" in response_json:
        edited_scenes: list[dict] = response_json.get("edited_scenes") or []
        overall_feedback: str = response_json.get("overall_feedback", "") or ""

        # Collect feedback
        feedback: list[dict] = []
        if overall_feedback:
            feedback.append({"scope": "overall", "ref": "", "text": overall_feedback})

        # Build slug→index map for existing scenes
        slug_to_index: dict[str, int] = {}
        for idx, scene in enumerate(scenes):
            title = scene.get("title", "")
            slug_to_index[_title_slug(title)] = idx

        # Determine first persona key from the spec
        personas: dict = raw.get("personas", {})
        first_persona = next(iter(personas), "")

        # Counters
        updated = 0
        added = 0
        deleted = 0
        features_changed = 0

        needs_grounding: list[str] = []

        # Track which existing scene indices to keep (complement of deleted)
        indices_to_delete: set[int] = set()

        for es in edited_scenes:
            scene_id: str = es.get("id", "")
            scene_title: str = es.get("title", "")
            narration: str = es.get("narration", "")
            is_deleted: bool = bool(es.get("deleted", False))
            scene_feedback: str = es.get("feedback", "") or ""
            payload_features: list[dict] = es.get("features") or []

            if scene_id.startswith("new-"):
                if is_deleted:
                    # New scene marked deleted — just skip it
                    continue
                # ADD new scene
                new_features: list[dict] = []
                existing_feat_ids: set[str] = set()
                for f in payload_features:
                    feat_id = f.get("id", "")
                    feat_desc = f.get("description", "")
                    feat_verify = f.get("verify", "")
                    feat_feedback = f.get("feedback", "") or ""
                    if feat_id.startswith("new-"):
                        feat_id = _generate_feature_id(feat_desc, existing_feat_ids)
                    existing_feat_ids.add(feat_id)
                    new_features.append({
                        "id": feat_id,
                        "description": feat_desc,
                        "verify": feat_verify,
                    })
                    if feat_feedback:
                        feedback.append({
                            "scope": "feature",
                            "ref": feat_id,
                            "text": feat_feedback,
                        })

                new_scene: dict = {
                    "persona": first_persona,
                    "title": scene_title,
                    "show": narration,
                    "concept_claim": narration,
                    "provenance": "",
                    "design_intent": None,
                    "features": new_features,
                }
                scenes.append(new_scene)
                # Update slug map for the newly added scene
                slug_to_index[_title_slug(scene_title)] = len(scenes) - 1
                needs_grounding.append(scene_title)
                added += 1
                features_changed += len(new_features)

                if scene_feedback:
                    feedback.append({
                        "scope": "scene",
                        "ref": _title_slug(scene_title),
                        "text": scene_feedback,
                    })

            else:
                # Existing scene
                idx = slug_to_index.get(scene_id)
                if idx is None:
                    # Unknown slug — silently skip
                    continue

                if is_deleted:
                    indices_to_delete.add(idx)
                    deleted += 1
                    continue

                # UPDATE existing scene
                scene_dict = scenes[idx]
                old_claim = scene_dict.get("concept_claim", "")
                if narration and old_claim != narration:
                    scene_dict["concept_claim"] = narration
                    updated += 1

                # Reconcile features
                existing_features: list[dict] = scene_dict.get("features") or []
                existing_feat_map: dict[str, dict] = {
                    f.get("id", ""): f for f in existing_features
                }
                payload_feat_ids: set[str] = set()
                new_feature_list: list[dict] = []
                all_feat_ids: set[str] = set(existing_feat_map.keys())

                for f in payload_features:
                    feat_id = f.get("id", "")
                    feat_desc = f.get("description", "")
                    feat_verify = f.get("verify", "")
                    feat_feedback = f.get("feedback", "") or ""

                    if feat_id.startswith("new-"):
                        feat_id = _generate_feature_id(feat_desc, all_feat_ids)
                        all_feat_ids.add(feat_id)
                        new_feature_list.append({
                            "id": feat_id,
                            "description": feat_desc,
                            "verify": feat_verify,
                        })
                        features_changed += 1
                    else:
                        payload_feat_ids.add(feat_id)
                        if feat_id in existing_feat_map:
                            existing_f = existing_feat_map[feat_id]
                            changed = False
                            if feat_desc and existing_f.get("description") != feat_desc:
                                existing_f["description"] = feat_desc
                                changed = True
                            if feat_verify and existing_f.get("verify") != feat_verify:
                                existing_f["verify"] = feat_verify
                                changed = True
                            if changed:
                                features_changed += 1
                            new_feature_list.append(existing_f)
                        else:
                            # New feature with explicit id
                            new_feature_list.append({
                                "id": feat_id,
                                "description": feat_desc,
                                "verify": feat_verify,
                            })
                            features_changed += 1

                    if feat_feedback:
                        feedback.append({
                            "scope": "feature",
                            "ref": feat_id,
                            "text": feat_feedback,
                        })

                # Features in spec but absent from payload → removed (not appended)
                removed_count = len(existing_feat_map) - len(
                    [k for k in existing_feat_map if k in payload_feat_ids]
                )
                if removed_count > 0:
                    features_changed += removed_count

                scene_dict["features"] = new_feature_list
                scenes[idx] = scene_dict

                if scene_feedback:
                    feedback.append({
                        "scope": "scene",
                        "ref": scene_id,
                        "text": scene_feedback,
                    })

        # Remove deleted scenes (in reverse index order to preserve positions)
        for idx in sorted(indices_to_delete, reverse=True):
            scenes.pop(idx)

        raw["scenes"] = scenes

        # ------------------------------------------------------------------
        # build_order: read from response, validate against surviving scenes,
        # drop deleted slugs, append newly-added scene slugs.
        # ------------------------------------------------------------------
        surviving_slugs: set[str] = {
            _title_slug(s.get("title", "")) for s in scenes
        }
        # Slugs of scenes that were newly added in this edit cycle
        newly_added_slugs: list[str] = [
            _title_slug(t) for t in needs_grounding
        ]
        response_build_order: list[str] | None = response_json.get("build_order")
        if response_build_order is not None:
            # Keep only slugs that map to surviving scenes (drops deleted + unknown ones)
            build_order_out: list[str] = [
                slug for slug in response_build_order if slug in surviving_slugs
            ]
            # Append newly-added scene slugs not already in the list
            listed_set: set[str] = set(build_order_out)
            for slug in newly_added_slugs:
                if slug not in listed_set and slug in surviving_slugs:
                    build_order_out.append(slug)
                    listed_set.add(slug)
        else:
            # No build_order in response: preserve the spec's existing value,
            # but still append newly-added scene slugs at the end.
            existing_bo: list[str] = raw.get("build_order") or []
            # Drop any slugs that no longer map to surviving scenes
            build_order_out = [s for s in existing_bo if s in surviving_slugs]
            listed_set = set(build_order_out)
            for slug in newly_added_slugs:
                if slug not in listed_set and slug in surviving_slugs:
                    build_order_out.append(slug)
                    listed_set.add(slug)

        raw["build_order"] = build_order_out
        spec_path.write_text(
            yaml.dump(raw, default_flow_style=False, allow_unicode=True)
        )

        return {
            "decision": decision,
            "applied": {
                "updated": updated,
                "added": added,
                "deleted": deleted,
                "features_changed": features_changed,
                "personas_changed": personas_changed,
                "why_brief_changed": why_brief_changed,
            },
            "needs_grounding": needs_grounding,
            "feedback": feedback,
            "build_order": build_order_out,
        }

    # ------------------------------------------------------------------
    # LEGACY shape: narration_edits
    # ------------------------------------------------------------------
    narration_edits: dict[str, str] = response_json.get("narration_edits", {}) or {}

    # Build a slug→scene-index mapping from the on-disk spec
    slug_to_index_legacy: dict[str, int] = {}
    for idx, scene in enumerate(scenes):
        title = scene.get("title", "")
        slug_to_index_legacy[_title_slug(title)] = idx

    edited = 0
    for slug, new_claim in narration_edits.items():
        idx = slug_to_index_legacy.get(slug)
        if idx is None:
            # Unknown slug — silently skip
            continue
        if scenes[idx].get("concept_claim") != new_claim:
            scenes[idx]["concept_claim"] = new_claim
            edited += 1

    # ------------------------------------------------------------------
    # build_order (legacy path): read from response, validate against
    # surviving scenes, preserve existing spec value when not provided.
    # ------------------------------------------------------------------
    surviving_slugs_legacy: set[str] = {
        _title_slug(s.get("title", "")) for s in scenes
    }
    response_build_order_legacy: list[str] | None = response_json.get("build_order")
    if response_build_order_legacy is not None:
        # Filter to only surviving slugs (ignore unknown/bogus ones)
        build_order_legacy: list[str] = [
            slug for slug in response_build_order_legacy
            if slug in surviving_slugs_legacy
        ]
        # Append any surviving scene slugs not already listed
        listed_legacy: set[str] = set(build_order_legacy)
        for scene in scenes:
            slug = _title_slug(scene.get("title", ""))
            if slug not in listed_legacy:
                build_order_legacy.append(slug)
                listed_legacy.add(slug)
        raw["build_order"] = build_order_legacy
    else:
        # Preserve whatever the spec already has (may be absent)
        build_order_legacy = raw.get("build_order") or []

    # Write back (only if there were edits OR build_order changed, but always write to keep round-trip clean)
    if edited > 0 or response_build_order_legacy is not None or personas_changed > 0:
        raw["scenes"] = scenes
        spec_path.write_text(
            yaml.dump(raw, default_flow_style=False, allow_unicode=True)
        )

    return {
        "decision": decision,
        "applied": {
            "updated": edited,
            "added": 0,
            "deleted": 0,
            "features_changed": 0,
            "personas_changed": personas_changed,
            "why_brief_changed": why_brief_changed,
        },
        "needs_grounding": [],
        "feedback": [],
        # back-compat key
        "edited": edited,
        "build_order": build_order_legacy,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def load_why_brief(spec_path: str | Path, spec: UnifiedSpec) -> dict:
    """Load the why-brief dict referenced by ``spec.why_brief`` (a path relative
    to the spec file).  Returns ``{}`` if no why_brief is declared or it can't be
    read/parsed — the review surface degrades gracefully without it.
    """
    if not spec.why_brief:
        return {}
    wb_path = (Path(spec_path).parent / spec.why_brief).resolve()
    try:
        data = yaml.safe_load(wb_path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _cmd_post(spec_path_str: str, run_id: str) -> None:
    """Post the narrative review request and print {id, url, share_token}."""
    from scripts.ddd import review as rv  # local import — network-touching

    spec_path = Path(spec_path_str)
    if not spec_path.exists():
        print(f"ERROR: spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    raw = yaml.safe_load(spec_path.read_text())
    spec = UnifiedSpec.model_validate(raw)
    why_brief = load_why_brief(spec_path, spec)
    request = build_narrative_review_request(spec, run_id, why_brief=why_brief)
    result = rv.post_review_request(request)
    print(json.dumps(result))


def _cmd_apply(spec_path_str: str, response_json_file: str) -> None:
    """Apply narration edits from a response JSON file and print the result dict."""
    response_path = Path(response_json_file)
    if not response_path.exists():
        print(f"ERROR: response JSON file not found: {response_path}", file=sys.stderr)
        sys.exit(1)

    response_json = json.loads(response_path.read_text())
    result = apply_narrative_edits(spec_path_str, response_json)
    print(json.dumps(result))


def main() -> None:
    """Entry point for ``python -m scripts.ddd.narrative``."""
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  python -m scripts.ddd.narrative post <spec_path> <run_id>\n"
            "  python -m scripts.ddd.narrative apply <spec_path> <response_json_file>",
            file=sys.stderr,
        )
        sys.exit(2)

    subcmd = sys.argv[1]

    if subcmd == "post":
        if len(sys.argv) != 4:
            print(
                "Usage: python -m scripts.ddd.narrative post <spec_path> <run_id>",
                file=sys.stderr,
            )
            sys.exit(2)
        _cmd_post(sys.argv[2], sys.argv[3])

    elif subcmd == "apply":
        if len(sys.argv) != 4:
            print(
                "Usage: python -m scripts.ddd.narrative apply <spec_path> <response_json_file>",
                file=sys.stderr,
            )
            sys.exit(2)
        _cmd_apply(sys.argv[2], sys.argv[3])

    else:
        print(f"ERROR: unknown subcommand {subcmd!r}. Use 'post' or 'apply'.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
