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
    narrative_slug: str
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

    ``seconds`` is a per-action timeout override. The recorder's default
    ``wait_for`` timeout is ``RecorderConfig.wait_for_timeout_ms`` (12s);
    when an author knows a particular condition might take longer (an SSE
    bulk-create stream that runs 30-90s) the spec can say
    ``seconds: 120`` to wait up to two minutes — and the recorder exits
    the moment the target appears, instead of holding blindly. The
    alternative — padding with a fixed ``hold`` after a normal-timeout
    ``wait_for`` — guarantees 100+ seconds of dead-air on a clip if the
    condition resolves early. ``None`` preserves the default.
    """

    kind: Literal["wait_for"]
    target: str
    seconds: float | None = None


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

    Set ``tool`` to the draw-tool button (e.g. ``css:.mapbox-gl-draw_polygon``) and
    ``draw`` activates it first with a coordinate mouse-click — which works on the
    small map-control buttons that a normal ``click`` can't (Playwright's
    actionability checks time out on them). Omit ``tool`` if the tool is already
    active.
    """

    kind: Literal["draw"]
    target: str
    points: list[tuple[float, float]]
    tool: str | None = None


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
    viewport: dict[str, int] | None = None
    """Optional per-scene viewport override (``{"width": int, "height": int}``).

    Default ``None`` → the scene renders at the spec-level
    ``video_viewport_width`` × ``video_viewport_height``. Set this on a single
    dense scene that needs more room (a Mapbox-heavy plan-review with a wide
    inspector panel, for example) without inflating the whole recording — the
    other scenes keep their original size and the spec author doesn't bump
    five scenes to fix one.

    Recording-canvas note: the mp4's frame size is fixed at context creation
    (``record_video_size``) — Playwright cannot change it mid-stream. A
    per-scene viewport override changes the LAYOUT viewport (and the page's
    CSS pixel dimensions) for that scene only, with the frame letterboxed /
    re-fitted into the spec-level canvas. After the scene's ``final_hold_ms``
    the recorder restores the spec-level viewport so subsequent scenes are
    unaffected.

    Authoring example::

        scenes:
          - title: "Dana drills into the plan map"
            url: "/microplans/program/133/plan/3536/review/"
            viewport: { width: 1440, height: 900 }  # this scene needs more room
            actions: ...
    """
    full_page: bool | None = None
    """Optional per-scene snapshot capture mode. Default ``None`` → full-page
    screenshot. Set ``false`` for a page that is a tall TABLE plus a map/chart
    (e.g. the plan-review page) so the snapshot is just the viewport and the
    map/chart is the hero — a full-page capture of such a page yields a 16,000px
    strip in which the map is a ~4% sliver (looks blank but rendered fine). A
    full-viewport map page (a group overlay map) captures correctly either way,
    so this only matters for table-dominant pages. WebGL/Mapbox itself renders +
    composites headlessly via the recorder's SwiftShader flags given a long
    enough ``hold`` for tiles to paint — see ddd-spec "Map / WebGL scenes"."""
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
    narrative_locked: bool = False
    """When True, this narrative has been approved at the narrative-agreement gate
    and is durable INPUT — ddd-spec must NOT regenerate it, and a new run reuses
    the whole spec (narrative paragraph, every scene's narrative/show/design_intent/
    features/actions) verbatim. Only an explicit ``redraft`` clears the lock. Set by
    ``apply_narrative_edits`` on ``approve``; the flag lives in the spec file so it
    travels with the narrative artifact. See ``narrative.is_narrative_locked``."""
    narrative_locked_at: str | None = None
    """ISO-8601 timestamp the narrative was locked (set alongside narrative_locked)."""
    # Sync stamps (0.2.176). canopy-web is the source of truth for the narrative
    # (overview + scene beats + personas + build_order); these record which web
    # version this local spec was last hydrated-from / pushed-to, so `narrative
    # pull` can tell "web advanced" from "local edited" and refuse to clobber
    # local narrative edits that haven't been pushed. The hash covers ONLY the
    # web-owned narrative fields — editing the disk-only render recipe
    # (show/actions/url) never counts as a narrative change.
    narrative_synced_version: int | None = None
    """The canopy-web narrative version this local spec was last in sync with."""
    narrative_synced_hash: str | None = None
    """Hash of the web-owned narrative fields at the last sync (see
    ``narrative.narrative_content_hash``). Differs from the current hash ⟺ the
    local narrative has been edited since the last pull/push."""
    narrative_synced_at: str | None = None
    """ISO-8601 timestamp of the last pull/push sync."""
    tagline: str = ""
    """One plain-language sentence: what this is + who it's for. The uploaded docs
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
    status: Literal["built", "new"] = "new"
    """Whether this beat's underlying capability already exists (``built``) or is
    work still to do (``new``, the "frontier"). Derived (not authored) at
    review-build time from the why-brief, mirroring canopy-web's
    ``sceneIsFrontier``: a beat is ``new`` when its ``provenance`` spine item is a
    gap (status != ``grounded``) OR a why-brief gap references it by
    ``claim_ref``; otherwise ``built``. Lets the BUILD SEQUENCE panel label
    already-shipped beats so the reviewer is not asked to "build" what is already
    live. Defaults to ``new`` (safe: shows as to-do) when there is no why-brief or
    the provenance is absent from the spine."""


class ReviewRequest(BaseModel):
    schema_version: int = 1
    run_id: str
    narrative_slug: str = ""
    """The narrative this review belongs to — the explicit source of truth
    canopy-web files the review under (``request_json.narrative_slug``). Sending
    it decouples narrative identity from ``run_id`` slug-parsing, so a run whose
    ``run_id`` slug differs from its narrative_slug (e.g. after a mid-flow
    rename) still groups with the right narrative. Defaults to "" → canopy-web
    falls back to ``narrative_slug_from_run_id(run_id)``."""
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
    narrative_slug: str
    # "promoted" is a legacy alias for "uploaded" — accepted on read so older
    # on-disk run_state.yaml files still validate; new runs write "uploaded".
    phase: Literal[
        "phase0", "spec", "render", "judged", "converged", "uploaded", "promoted"
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
    # /canopy:ddd-upload refuses any run with scene_filter != None.
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
    # Hosted narrative-review URL (0.2.150). Stamped by the ddd-narrative-review
    # gate after it posts the narrative to the canopy-web review surface — the
    # token-bearing /review/<id>/?t=<token> link the user approved. ddd-run's
    # upload step passes it as the video's `narrative` companion link so a
    # viewer watching the clip can jump back to the story that generated it.
    narrative_review_url: str | None = None
    # Hosted narrative-review ID (0.2.172). Stamped alongside narrative_review_url
    # by the ddd-narrative-review gate's `narrative post` command — the raw
    # ReviewRequest UUID, so ddd-upload can attach this run's artifacts to the
    # exact narrative version without regex-parsing it back out of the URL.
    # Its presence is also the upload gate's proof that a narrative review ran:
    # when it's None, upload re-verifies against canopy-web and refuses to
    # publish a run that has no narrative (see scripts/ddd/upload.py).
    narrative_review_id: str | None = None
