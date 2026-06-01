"""Canonical Pydantic v2 schemas for demo-driven-development v3 (ddd-v3).

All models are defined here.  Import them from this module or from
``scripts.ddd.schemas`` (re-exported via ``__init__.py``).
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

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
    "draw",        # draw a polygon on a map/canvas (target=element, points=[[fx,fy],...] fractions)
)


class _ActionBase(BaseModel):
    """Shared fields for every action verb.

    ``extra="forbid"`` is the whole point of the discriminated union — a spec
    that puts ``target`` on a ``type`` action (or ``value`` on a ``click``)
    used to silently no-op at runtime; now it fails validation with the
    field name and the action it lives on. The dispatcher (``execute_action``)
    still accepts the raw dict at runtime so legacy callers that bypass the
    schema keep working.
    """

    model_config = ConfigDict(extra="forbid")

    note: str | None = None
    """Human note: what this step demonstrates (shown in render logs)."""

    must_succeed: bool = False
    """When True, the recorder raises (not just logs) if this action fails.

    Use for the "without this, the rest of the scene is nonsense" steps —
    the bulk-create button click whose state is the whole rest of the demo.
    Defaults to False (log + continue, one bad action never aborts the render).
    """


class GotoAction(_ActionBase):
    """Navigate to a URL. ``target`` is the URL (absolute or path-relative)."""

    kind: Literal["goto"]
    target: str


class ClickAction(_ActionBase):
    """Click a visible text label or CSS selector.

    ``target`` supports the recorder's prefix syntax: ``css:#sel``,
    ``testid:foo``, ``aria:Foo``, ``role:button``, ``text:Foo`` (force the
    visible-text path). Bare strings use a heuristic — CSS-shaped → selector
    engine; English → visible-text ranking.
    """

    kind: Literal["click"]
    target: str


class ClickMenuAction(_ActionBase):
    """Click an item inside the currently-open dropdown / popover.

    Same target syntax as :class:`ClickAction`. Distinct verb because menus
    usually have shorter post-click settle than a top-level button.
    """

    kind: Literal["click_menu"]
    target: str


class FillAction(_ActionBase):
    """Focus a field (``target``) and type ``value`` character-by-character.

    Typing fires real ``input`` events — reactive form widgets that gate
    buttons on debounced input (e.g. the bulk-create line counter) WILL
    react to ``fill`` but won't react to a raw ``.value = ...`` setter.
    """

    kind: Literal["fill"]
    target: str
    value: str


class SelectAction(_ActionBase):
    """Pick an option from a native ``<select>``.

    ``value`` is interpreted as the option's ``value`` attribute first, then
    a digit-only string as the 0-based ``index``, then the visible text
    label. The recorder glides the cursor onto the select so the viewer
    sees which control is being driven (the dropdown won't visually open —
    native-control limitation).
    """

    kind: Literal["select"]
    target: str
    value: str


class TypeAction(_ActionBase):
    """Type ``value`` into whatever element currently has focus.

    No ``target`` — that's what :class:`FillAction` is for. Use ``type``
    only after an explicit focus (or right after ``fill`` to extend the
    text).
    """

    kind: Literal["type"]
    value: str


class PressAction(_ActionBase):
    """Press a keyboard key. Defaults to Enter — the most common case."""

    kind: Literal["press"]
    value: str = "Enter"


class HoverAction(_ActionBase):
    """Glide the cursor onto ``target`` and rest. No click.

    ``seconds`` overrides the default dwell — useful when the demo is
    showing a tooltip or hover-revealed control that needs time to appear.
    """

    kind: Literal["hover"]
    target: str
    seconds: float | None = None


class ScrollToAction(_ActionBase):
    """Smooth-scroll the element matching ``target`` into view."""

    kind: Literal["scroll_to"]
    target: str


class ScrollAction(_ActionBase):
    """Scroll the page. ``value`` is ``"top"``, ``"bottom"``, or a pixel offset."""

    kind: Literal["scroll"]
    value: str = "bottom"


class WaitForAction(_ActionBase):
    """Wait for ``target`` (text or selector) to appear.

    All-digits target is treated as a millisecond pause. Plain-text targets
    skip the selector engine (which would otherwise sit through its full
    timeout before falling back) — see the recorder's
    ``_lib/targets.wait_for_target``.
    """

    kind: Literal["wait_for"]
    target: str


class HoldAction(_ActionBase):
    """Dwell in place for ``seconds``.

    The single-purpose pause: framing time after a layout, reading time
    after a render, slack so the SSE stream finishes flushing.
    """

    kind: Literal["hold"]
    seconds: float


class DrawAction(_ActionBase):
    """Draw a polygon on a map or canvas by clicking a sequence of points.

    The recorder has no way to express map drawing through the other verbs —
    ``click`` resolves a DOM element's centre, but a Mapbox-GL-Draw polygon (or any
    canvas drawing tool) needs clicks at *coordinates on the canvas*, not on a
    labelled element. ``draw`` fills that gap.

    ``target`` is the map/canvas element (e.g. ``css:#review-map``). ``points`` is a
    list of ``[fx, fy]`` fractional positions (0-1) within that element's bounding
    box — fractions, not pixels, so the polygon is independent of viewport size. The
    synthetic cursor glides to each vertex and clicks (real Playwright pointer events
    the drawing tool receives), then double-clicks the last vertex to close the
    polygon (Mapbox finishes a polygon on double-click).

    Activate the drawing tool first — a normal ``click`` on its toolbar button (e.g.
    ``css:.mapbox-gl-draw_polygon``) — then ``draw`` places the vertices.
    """

    kind: Literal["draw"]
    target: str
    points: list[tuple[float, float]]


# Discriminated union: Pydantic picks the right subclass from ``kind`` alone.
# Existing YAML specs (lists of dicts with ``kind: ...`` + the verb's fields)
# validate against this without any spec edits — all real-world action shapes
# I surveyed across 38 specs already match the strict per-verb classes.
Action = Annotated[
    Union[
        GotoAction, ClickAction, ClickMenuAction, FillAction, SelectAction,
        TypeAction, PressAction, HoverAction, ScrollToAction, ScrollAction,
        WaitForAction, HoldAction, DrawAction,
    ],
    Field(discriminator="kind"),
]


# Tuple form of the action classes — used by the single-source guard test
# that asserts ACTION_KINDS, the Pydantic kind Literals, and the dispatch
# table never drift.
ACTION_CLASSES: tuple[type[_ActionBase], ...] = (
    GotoAction, ClickAction, ClickMenuAction, FillAction, SelectAction,
    TypeAction, PressAction, HoverAction, ScrollToAction, ScrollAction,
    WaitForAction, HoldAction, DrawAction,
)


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
    url: str | None = None
    """Optional explicit starting URL for this scene (absolute or path-relative
    to the spec's ``base_url``).

    Resolution order in the recorder:
      1. This ``url`` field — the cleanest authoring path; declarative.
      2. The first ``goto`` in ``actions`` — implicit, but easy to read.
      3. ``None`` — the recorder stays on the previous scene's ending URL.

    The ``None`` default makes multi-scene narratives work without a hardcoded
    URL map: "scene 2 clicks a link that navigates → scene 3 continues from
    there" needs no URL on scene 3. Authors who want a hard reset between
    scenes use either this ``url`` or an explicit ``goto`` action."""
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
