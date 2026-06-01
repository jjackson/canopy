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


# Action verbs the recorder understands. Single source of truth — the recorder
# imports this tuple, and the ``Action.kind`` Literal below is unpacked from
# it so Pydantic validation and the dispatcher vocabulary can never drift.
# Keep ordering loosely by frequency-of-use (navigation + click first).
ACTION_KINDS: tuple[str, ...] = (
    "goto",        # navigate to a url (target=url)
    "click",       # click a visible text label or CSS selector (target)
    "click_menu",  # click an item inside the currently-open dropdown (target=item text)
    "fill",        # focus a field (target=label/selector) and type value
    "select",      # pick from a native <select> (target=select, value=attr/index/label)
    "type",        # type value into whatever is focused
    "press",       # press a key (value, e.g. "Enter")
    "hover",       # glide the cursor onto target and rest (no click)
    "scroll_to",   # smooth-scroll target into view
    "scroll",      # scroll the page (value: "bottom" | "top" | "<px>")
    "wait_for",    # wait for target text/selector to appear, or value=ms
    "hold",        # dwell in place for seconds (value or seconds)
)


class Action(BaseModel):
    """One scripted interaction the recorder performs with the synthetic cursor.

    A scene's ``actions`` turn its free-text ``show`` into something the video
    actually DOES — click, fill, open a menu, dwell, scroll — so the recording
    demonstrates the feature being used instead of just panning a static page.
    The recorder (scripts/walkthrough/_lib/recorder.py) maps each Action onto a
    cursor primitive; unknown kinds are skipped, never fatal.

    Fields (all optional except ``kind``):
      kind         — one of :data:`ACTION_KINDS`
      target       — text label or CSS selector to act on. Supports prefix syntax:
                     ``css:#sel``, ``testid:foo``, ``aria:Foo``, ``role:button``,
                     ``text:Foo`` (force the visible-text path). Bare strings use
                     a heuristic (CSS-shaped → selector engine; English → text).
      value        — text to fill/type, key to press, url to goto, "bottom"/"top"/px
                     for scroll, OR the ``<select>`` option's value attribute /
                     0-based index / visible label for ``select``
      seconds      — dwell/hold duration
      note         — human note: what this step demonstrates (shown in render logs)
      must_succeed — when True, the recorder raises (not just logs) if this
                     action fails. Use for the "without this, the rest of the
                     scene is nonsense" steps. Defaults to False (log + continue).
    """

    kind: Literal[
        "goto", "click", "click_menu", "fill", "select", "type", "press",
        "hover", "scroll_to", "scroll", "wait_for", "hold",
    ]
    target: str | None = None
    value: str | None = None
    seconds: float | None = None
    note: str | None = None
    must_succeed: bool = False


class Scene(BaseModel):
    persona: str
    title: str
    show: str
    concept_claim: str
    provenance: str
    design_intent: str | None = None
    impressive_because: str | None = None
    features: list[Feature] = []
    actions: list[Action] = []
    """Scripted cursor interactions for the recorder — see ``Action``. Optional:
    a scene with no ``actions`` falls back to the legacy scroll-pan. Declaring
    actions is what makes a rendered demo show the feature being operated (and is
    what lifts the ``feature_use`` score off the floor)."""
    narrative: str = ""
    """Canonical per-scene narrative text — the story beat the reviewer reads.
    May be one OR MORE sentences (per gap-flexible-scene-length). When set, it
    takes precedence over sentence-split-of-spec.narrative-by-position for both
    the review UI and the apply-edits writeback. When empty (legacy / first
    edit not yet made), the renderer falls back to splitting ``UnifiedSpec.narrative``
    by sentence and taking the i-th sentence."""


class UnifiedSpec(BaseModel):
    name: str
    narrative: str
    base_url: str
    auth: dict | None = None
    why_brief: str | None = None
    personas: dict[str, Persona]
    scenes: list[Scene]
    tagline: str = ""
    """One plain-language sentence: what this is + who it's for. The promoted docs
    page leads with it so a newcomer understands the feature before pressing play.
    The build-audience narrative/concept_claims are NOT a substitute (they carry
    internal jargon); this is the user-facing hook."""
    capabilities: list[str] = []
    """User-facing 'what you can do' bullets, phrased as the reader's benefits/outcomes
    (not the build-audience concept_claims). The docs page uses these for the
    capabilities section when present, falling back to concept_claims otherwise."""
    why_summary: str = ""
    """A short, plain-language 'why this matters' for the docs page (a couple of
    sentences, no internal jargon). The docs page uses this for the Why section when
    present, instead of the build-audience why_brief problem + spine."""
    getting_started: list[str] = []
    """Ordered, user-facing 'how do I start' steps for the docs page (what to run /
    do, in the reader's terms) — distinct from each scene's ``show`` (which is the
    demo's on-screen walkthrough, not adoption instructions)."""
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
    provenance: str = ""  # spine id this beat grounds — lets the surface co-locate grounding
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
    # Scene-filter metadata (0.2.128). A full-spec run sets scenes_run to the
    # complete list of spec indices and scene_filter to None. A partial run
    # (--scene <selector> on /canopy:ddd-run or /canopy:walkthrough) sets
    # scenes_run to the rendered subset and scene_filter to the raw selector.
    # /canopy:ddd-promote refuses any run with scene_filter != None.
    scenes_run: list[int] | None = None
    scene_filter: str | None = None
    # Auto-iterate signal (0.2.131). Computed by /canopy:ddd-run Step 5 after
    # the dual-judge verdict comes back; consumed by the /canopy:ddd
    # orchestrator's Converge-or-loop branch. Possible values:
    #   continue              — all non-DEFER findings are fix_kind=mechanical;
    #                           orchestrator may apply fixes and re-fire.
    #   stop_done             — converged; full-spec; ready for promotion.
    #   stop_partial          — converged on filtered scope; drop --scene to
    #                           promote.
    #   stop_concept_change   — a CONCEPT/redesign finding present; needs the
    #                           irreplaceable-taste pause.
    #   stop_unclear          — non-DEFER finding with fix_kind=options or
    #                           redesign; needs user pick.
    #   stop_max_iter         — MAX_ITERATIONS would be exceeded.
    auto_iterate_next_action: str | None = None
    auto_iterate_reason: str | None = None
    # Hosted artifact URLs per iteration (0.2.135). Populated by
    # /canopy:ddd-run's render-then-upload step: each iteration's rendered
    # deck (and clip, when present) is auto-uploaded to canopy-web and the
    # returned URL is stamped here. Surfaced findings and review-request
    # gates reference these URLs directly — no manual upload needed at
    # surface-time, no local file:// paths leaking into messages that the
    # user reads on another device.
    #
    # Shape:
    #   iteration_decks: {0: "https://canopy-web.../w/<uuid1>", 1: "<...>"}
    #   iteration_clips: {0: "https://canopy-web.../w/<uuid2>", 1: "<...>"}
    #
    # Deep-link to a specific scene by appending "#scene-<N>" — the deck
    # generator emits id="scene-<N>" anchors on every scene slide using the
    # original spec index, so the anchor is stable across partial/full runs.
    iteration_decks: dict[int, str] = {}
    iteration_clips: dict[int, str] = {}
