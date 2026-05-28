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

from scripts.ddd.schemas.models import Decision, NarrationItem, ReviewRequest, UnifiedSpec


# ---------------------------------------------------------------------------
# Slug helper
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
            text=scene.concept_claim,
            features=scene.features,
        )
        for i, scene in enumerate(spec.scenes)
    ]

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
        autonomous_audit=[],
        decisions=[decision],
        actionability=actionability,
    )


# ---------------------------------------------------------------------------
# Disk-touching apply function
# ---------------------------------------------------------------------------


def apply_narrative_edits(
    spec_path: str | Path,
    response_json: dict,
) -> dict:
    """Apply narration edits from a resolved review response back onto the spec.

    Loads the spec YAML, applies ``response_json.get("narration_edits", {})``
    (keyed by the narration item ``id``, i.e. the scene-title slug) to the
    matching scene's ``concept_claim``, writes the spec back to disk, and
    returns ``{"decision": <str>, "edited": <int>}``.

    Unknown narration ids are silently skipped — the function is robust to
    partial or mis-keyed responses.

    Parameters
    ----------
    spec_path:
        Path to the unified spec YAML file.
    response_json:
        The ``response_json`` dict from the resolved review.  Expected shape::

            {
                "decisions": {"narrative-verdict": "approve" | "redraft"},
                "narration_edits": {"<scene-slug>": "<new concept_claim>", ...}
            }

        Legacy v2 values are accepted for safety and coerced to v3:
        ``"agree"``/``"edit"`` → ``"approve"``; ``"rethink"`` → ``"redraft"``.

    Returns
    -------
    dict
        ``{"decision": str, "edited": int}`` where ``decision`` is the
        normalised v3 value (``"approve"`` or ``"redraft"``) and ``edited``
        is the count of scenes whose ``concept_claim`` was changed.
    """
    spec_path = Path(spec_path)
    raw = yaml.safe_load(spec_path.read_text())

    narration_edits: dict[str, str] = response_json.get("narration_edits", {}) or {}
    decisions: dict[str, str] = response_json.get("decisions", {}) or {}
    raw_decision: str = decisions.get("narrative-verdict", "approve")

    # Normalise to v3 vocabulary: legacy "agree"/"edit" → "approve"; "rethink" → "redraft".
    # New values ("approve"/"redraft") pass through unchanged.
    _LEGACY_MAP = {
        "agree": "approve",
        "edit": "approve",
        "rethink": "redraft",
    }
    decision: str = _LEGACY_MAP.get(raw_decision, raw_decision)

    # Build a slug→scene-index mapping from the on-disk spec
    scenes: list[dict] = raw.get("scenes", [])
    slug_to_index: dict[str, int] = {}
    for idx, scene in enumerate(scenes):
        title = scene.get("title", "")
        slug_to_index[_title_slug(title)] = idx

    edited = 0
    for slug, new_claim in narration_edits.items():
        idx = slug_to_index.get(slug)
        if idx is None:
            # Unknown slug — silently skip
            continue
        if scenes[idx].get("concept_claim") != new_claim:
            scenes[idx]["concept_claim"] = new_claim
            edited += 1

    # Write back (only if there were edits, but always write to keep round-trip clean)
    if edited > 0:
        raw["scenes"] = scenes
        spec_path.write_text(
            yaml.dump(raw, default_flow_style=False, allow_unicode=True)
        )

    return {"decision": decision, "edited": edited}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _cmd_post(spec_path_str: str, run_id: str) -> None:
    """Post the narrative review request and print {id, url, share_token}."""
    from scripts.ddd import review as rv  # local import — network-touching

    spec_path = Path(spec_path_str)
    if not spec_path.exists():
        print(f"ERROR: spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    raw = yaml.safe_load(spec_path.read_text())
    spec = UnifiedSpec.model_validate(raw)
    request = build_narrative_review_request(spec, run_id)
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
