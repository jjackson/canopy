"""Canonical Pydantic v2 schemas for demo-driven-development v3 (ddd-v3).

All models are defined here.  Import them from this module or from
``scripts.ddd.schemas`` (re-exported via ``__init__.py``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# SP0.1 — WhyBrief schema
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    kind: Literal["documented", "implemented", "assumed"]
    ref: str


class SpineItem(BaseModel):
    id: str
    claim: str
    rationale: str
    evidence: list[Evidence] = []
    status: Literal["grounded", "gap"] = "gap"


class Gap(BaseModel):
    id: str
    type: Literal["RESEARCH", "CAPABILITY", "DECISION"]
    claim_ref: str
    detail: str
    proposed_action: str


class WhyBrief(BaseModel):
    schema_version: int = 1
    feature: str
    problem: str
    spine: list[SpineItem]
    gaps: list[Gap]


# ---------------------------------------------------------------------------
# SP0.2 — Remaining models
# ---------------------------------------------------------------------------


class Persona(BaseModel):
    name: str
    role: str
    color: str
    intro: str
    org: str = ""  # the organization this individual belongs to (e.g. "Dimagi", "LLO")


class Feature(BaseModel):
    """A single buildable, verifiable capability within a scene (DDD v3)."""

    id: str
    description: str  # concrete buildable unit — what to implement
    verify: str       # how to validate it's done (API assertion, UI state, test command)


class Scene(BaseModel):
    persona: str
    title: str
    show: str
    concept_claim: str
    provenance: str
    design_intent: str | None = None
    impressive_because: str | None = None
    features: list[Feature] = []


class UnifiedSpec(BaseModel):
    name: str
    narrative: str
    base_url: str
    auth: dict | None = None
    why_brief: str | None = None
    personas: dict[str, Persona]
    scenes: list[Scene]
    build_order: list[str] = []
    """Ordered list of scene-title slugs representing the tackle sequence.

    Empty = default to narrative (scene array) order.  Partial lists are
    allowed — unlisted scenes implicitly follow in scene order.  The slugs
    must match those produced by ``_title_slug(scene.title)`` in
    ``scripts.ddd.narrative``.
    """


class Dimension(BaseModel):
    score: float
    weight: float


class Verdict(BaseModel):
    schema_version: int = 1
    dimensions: dict[str, Dimension]
    overall_score: float
    verdict: Literal["pass", "warn", "fail", "blocked"]
    blocking_reason: str | None = None
    fix_recommendation: str | None = None


class Decision(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    prompt: str
    options: list[str]
    recommended: str
    class_: str = Field(alias="class")


class NarrationItem(BaseModel):
    """One scene's narration entry in a ReviewRequest (DDD v3).

    Carries the scene's 1-based number (``scene``), its slug (``id``), the
    story-beat ``title``, the on-screen ``persona`` key, the editable story
    beat (``text`` = concept_claim), and the concrete buildable features
    declared by the spec's ``Scene.features[]``.  ``title``/``persona`` let
    the review surface render the cohesive multi-persona narrative instead of
    a generic "Scene N" label.
    """

    scene: int
    id: str
    title: str = ""
    persona: str = ""
    text: str
    features: list[Feature] = []


class ReviewRequest(BaseModel):
    schema_version: int = 1
    run_id: str
    gate: str
    video: dict
    decisions: list[Decision]
    narration: list[NarrationItem | dict]
    narrative: str = ""
    """The cohesive demo narrative — the whole story the scenes decompose.

    Rendered at the top of the review surface so the reviewer reads the arc
    before the per-scene breakdown.  Populated from ``UnifiedSpec.narrative``.
    """
    personas: dict = {}
    """Persona key -> {name, role, color, intro, org}, so the surface can show who
    is on screen in each scene (multi-persona handoffs).  From ``UnifiedSpec.personas``."""
    why_brief: dict = {}
    """The resolved why-brief (problem, spine[], gaps[]) so the review surface can
    show + edit the grounding doc alongside the narrative.  Loaded by the caller
    from ``UnifiedSpec.why_brief`` (a path relative to the spec file)."""
    autonomous_audit: list[str] = []
    actionability: dict | None = None
    build_order: list[str] = []
    """Ordered list of scene-title slugs representing the user's chosen tackle sequence.

    Populated by ``build_narrative_review_request`` from ``spec.build_order``
    (or defaulted to scene order when the spec has no explicit order).  The
    editor returns this field in its response_json and ``apply_narrative_edits``
    persists it back onto the spec.
    """


class RunState(BaseModel):
    schema_version: int = 1
    run_id: str
    feature: str
    phase: Literal[
        "phase0", "spec", "render", "judged", "converged", "promoted"
    ] = "phase0"
    iteration: int = 0
    why_brief: str | None = None
    verdicts: dict[str, str] = {}
    findings: list[dict] = []
    pending_review: str | None = None
    last_actor: str | None = None
    last_actor_at: str | None = None
