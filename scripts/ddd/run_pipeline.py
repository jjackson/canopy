"""DDD run-pipeline glue — SP4.1 + SP4.2.

Assembles verdict paths and findings into a RunState, and decides convergence
from two judge verdicts (concept + user-artifact).

Public API
----------
assemble_run_state(state, concept_verdict, user_verdict, findings, *, concept_path, user_path) -> RunState
    Mutates state in place: sets verdicts, findings, and phase="judged".
    Returns the mutated state.

compute_convergence(concept_verdict, user_verdict, *, threshold) -> bool
    Returns True iff BOTH verdicts have overall_score >= threshold AND neither
    verdict is "blocked".  Threshold defaults to 4.0.

HARD_CAP
    Module constant: runaway backstop on refinement iterations. The loop is
    progress-aware (keep going while mechanical findings are still improving the
    score; stop on a stall/regression) — HARD_CAP only catches a pathological
    non-converging loop. See ``compute_auto_iterate``.
"""
from __future__ import annotations

from scripts.ddd.schemas.models import RunState, Verdict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Runaway backstop only — NOT the normal stop. The loop stops on real gates,
# options/redesign findings, or a score stall/regression long before this.
HARD_CAP: int = 10
# Back-compat alias for older callers; no longer a hard 3-iteration cap.
MAX_ITERATIONS: int = HARD_CAP


# ---------------------------------------------------------------------------
# SP4.1 — assemble_run_state
# ---------------------------------------------------------------------------


def assemble_run_state(
    state: RunState,
    concept_verdict: Verdict,
    user_verdict: Verdict,
    findings: list[dict],
    *,
    concept_path: str = "verdict-concept.yaml",
    user_path: str = "verdict-user.yaml",
    manifest: dict | None = None,
    extra_verdict_paths: dict[str, str] | None = None,
) -> RunState:
    """Assemble both verdict paths and merged findings into *state*.

    Mutates *state* in place (Pydantic v2 models are mutable by default) and
    returns it so callers can chain or ignore the return value.

    Parameters
    ----------
    state:
        The run's RunState.  Must already have a valid run_id and narrative_slug.
    concept_verdict:
        The Verdict produced by the ddd-concept-eval judge.
    user_verdict:
        The Verdict produced by the user-artifact judge (canopy:visual-judge
        with audience="narrative_slug user").
    findings:
        Merged list of design_finding dicts (from design_findings.json).
    concept_path:
        Path (relative to run dir or absolute) of the concept verdict YAML.
        Default: "verdict-concept.yaml".
    user_path:
        Path (relative to run dir or absolute) of the user-artifact verdict YAML.
        Default: "verdict-user.yaml".
    manifest:
        Optional render manifest (walkthrough-run-data.json). When provided, its
        ``scenes_run`` / ``scene_filter`` are carried onto the run state — the
        render engine is the single source of truth for which scenes were
        rendered, so the upload's partial-run guard reads what the engine
        actually emitted. When ``None``, those fields are left untouched.
    extra_verdict_paths:
        Optional additional verdict artifacts to record, keyed by verdict kind
        (e.g. ``{"timing": "verdict-timing.json", "why": "verdict-why.yaml"}``).
        Recorded alongside the gating pair in ``state.verdicts`` — the assembler
        is generic over kinds (canopy#265 item 1). The ``concept`` /
        ``user_artifact`` keys cannot be shadowed.

    Returns
    -------
    RunState
        The mutated *state* (same object).
    """
    state.verdicts = {
        **(extra_verdict_paths or {}),
        "concept": concept_path,
        "user_artifact": user_path,
    }
    state.findings = list(findings)
    state.phase = "judged"
    if manifest is not None:
        state.scenes_run = manifest.get("scenes_run")
        state.scene_filter = manifest.get("scene_filter")
    return state


# ---------------------------------------------------------------------------
# SP4.2 — compute_convergence
# ---------------------------------------------------------------------------


def compute_convergence_all(
    verdicts: dict[str, Verdict],
    *,
    threshold: float = 4.0,
) -> bool:
    """Generic convergence over N verdicts (canopy#265 item 1).

    Only verdicts with ``gate == "gating"`` participate; ``advisory`` verdicts
    (timing, video, why, actionability) are recorded and reported but a low
    score never blocks convergence. Every gating verdict must:

    1. have ``overall_score >= threshold``
    2. not be ``blocked``
    3. not carry ``live_state_verified is False`` — an eval whose grading anchor
       never touched live state cannot converge a run, whatever its score says
       (the out-of-chain fitness law, canopy#265 item 3). ``None`` (legacy
       emitters, unknown) is allowed for back-compat.

    Returns False when no gating verdict is present at all — convergence must be
    demonstrated, not defaulted.

    The weakest-link rule (embedded in each judge) means overall_score already
    reflects the lowest gating dimension, so checking overall_score is
    sufficient — no need to re-inspect individual dimensions here.
    """
    gating = {k: v for k, v in verdicts.items() if v.gate == "gating"}
    if not gating:
        return False
    for v in gating.values():
        if v.verdict == "blocked":
            return False
        if v.live_state_verified is False:
            return False
        if v.overall_score < threshold:
            return False
    return True


def compute_convergence(
    concept_verdict: Verdict,
    user_verdict: Verdict,
    *,
    threshold: float = 4.0,
    extra: dict[str, Verdict] | None = None,
) -> bool:
    """Return True iff the run's verdicts satisfy the convergence criteria.

    The documented two-verdict entry point — delegates to
    ``compute_convergence_all`` over the gating pair plus any ``extra`` verdicts
    (whose ``gate`` field decides whether they participate).

    claim_reality_coherence is advisory and excluded upstream from the judge's
    overall_score, so it does not appear here.

    Parameters
    ----------
    concept_verdict:
        Verdict from the ddd-concept-eval judge.
    user_verdict:
        Verdict from the user-artifact judge.
    threshold:
        Minimum overall_score required for every gating verdict.  Default: 4.0.
    extra:
        Optional additional verdicts by kind (e.g. from
        ``scripts.ddd.verdicts.load_verdict``).

    Returns
    -------
    bool
        True iff convergence criteria are satisfied; False otherwise.
    """
    return compute_convergence_all(
        {
            **(extra or {}),
            "concept": concept_verdict,
            "user_artifact": user_verdict,
        },
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Progress-aware auto-iterate (replaces the old raw MAX_ITERATIONS=3 stop)
# ---------------------------------------------------------------------------


def compute_auto_iterate(
    state: RunState,
    concept_verdict: Verdict,
    user_verdict: Verdict,
    findings: list[dict],
    *,
    converged: bool | None = None,
    hard_cap: int = HARD_CAP,
) -> tuple[str, str]:
    """Decide the next loop action from the SCORE TRAJECTORY, not an iteration count.

    DDD's point is to loop autonomously on mechanical findings until they're
    exhausted. A raw count stopped good runs mid-progress and was blind to
    regressions. This gates on whether the gating score is still improving:

    - converged (both judges >= threshold)        -> ``stop_done`` / ``stop_partial``
    - a CONCEPT/redesign finding                  -> ``stop_concept_change``
    - any options/redesign finding                -> ``stop_unclear``
    - score stalled/regressed over last 2 iters   -> ``stop_max_iter`` (needs a human)
    - hit ``hard_cap`` without converging         -> ``stop_max_iter`` (runaway backstop)
    - else (mechanical + still improving)         -> ``continue`` (keep looping)

    Mutates ``state.score_history`` (appends this iteration's gating score) and
    returns ``(action, reason)``. The gating score is the lower of the two
    judges' overall_score (claim_reality_coherence is already excluded upstream).
    """
    if converged is None:
        converged = compute_convergence(concept_verdict, user_verdict)

    score = min(concept_verdict.overall_score, user_verdict.overall_score)
    state.score_history = (state.score_history or []) + [float(score)]
    hist = state.score_history
    # "stalled" = the last two iterations produced no new best (no progress, or a
    # fix regressed another scene). Needs >=3 data points to judge a trend.
    stalled = (
        len(hist) >= 3 and hist[-1] <= max(hist[:-2]) and hist[-2] <= max(hist[:-2])
    )

    all_findings = [
        {"route": f.get("route", "PRODUCT"), "fix_kind": f.get("fix_kind", "options")}
        for f in findings
    ]
    for d in (user_verdict.dimensions or {}).values():
        if isinstance(d, dict) and d.get("fix_kind"):
            all_findings.append({"route": "PRODUCT", "fix_kind": d["fix_kind"]})
    non_defer = [f for f in all_findings if f["route"] != "DEFER"]
    mechanical = [f for f in non_defer if f["fix_kind"] == "mechanical"]
    unclear = [f for f in non_defer if f["fix_kind"] in ("options", "redesign")]

    if converged and not getattr(state, "scene_filter", None):
        return "stop_done", "Both judges passed full spec — ready for promotion."
    if converged and getattr(state, "scene_filter", None):
        return "stop_partial", "Both judges passed the filtered scope — drop --scene and re-fire."
    if any(f["route"] == "CONCEPT" and f["fix_kind"] == "redesign" for f in non_defer):
        return "stop_concept_change", "Concept-change finding — needs user judgment on direction."
    if stalled:
        return "stop_max_iter", (
            f"Score stalled/regressed across the last 2 iterations (history={hist}) — "
            "mechanical fixes aren't converging; needs a human look."
        )
    if len(hist) >= hard_cap:
        return "stop_max_iter", f"Hit the {hard_cap}-iteration backstop (history={hist})."
    # Autonomous until it can't be: APPLY every confident (mechanical) fix and
    # re-fire BEFORE surfacing anything uncertain. A `mechanical` finding is one
    # the loop can act on by itself, so it must never land in a human review just
    # because some *other* finding this iteration was uncertain. Keep looping
    # while mechanical fixes remain; only when nothing is left to auto-apply do
    # the options/redesign findings get surfaced. (The stall/cap checks above
    # still bound a mechanical loop that isn't converging.)
    if mechanical:
        return "continue", (
            f"{len(mechanical)} mechanical (confident) fix(es) remain — apply + re-fire "
            f"before surfacing any options (history={hist})."
        )
    if unclear:
        return "stop_unclear", (
            f"{len(unclear)} options/redesign finding(s) and no mechanical fixes left "
            "to auto-apply — surface ONLY these for a user pick."
        )
    return "continue", (
        f"No options/redesign and score still moving (history={hist}) — re-fire."
    )
