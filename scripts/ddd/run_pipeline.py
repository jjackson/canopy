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

MAX_ITERATIONS
    Module constant: maximum refinement iterations before the orchestrator
    surfaces a human-review checkpoint (used by the outer loop, not here).
"""
from __future__ import annotations

from scripts.ddd.schemas.models import RunState, Verdict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ITERATIONS: int = 3


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
) -> RunState:
    """Assemble both verdict paths and merged findings into *state*.

    Mutates *state* in place (Pydantic v2 models are mutable by default) and
    returns it so callers can chain or ignore the return value.

    Parameters
    ----------
    state:
        The run's RunState.  Must already have a valid run_id and feature.
    concept_verdict:
        The Verdict produced by the ddd-concept-eval judge.
    user_verdict:
        The Verdict produced by the user-artifact judge (canopy:visual-judge
        with audience="feature user").
    findings:
        Merged list of design_finding dicts (from design_findings.json).
    concept_path:
        Path (relative to run dir or absolute) of the concept verdict YAML.
        Default: "verdict-concept.yaml".
    user_path:
        Path (relative to run dir or absolute) of the user-artifact verdict YAML.
        Default: "verdict-user.yaml".

    Returns
    -------
    RunState
        The mutated *state* (same object).
    """
    state.verdicts = {
        "concept": concept_path,
        "user_artifact": user_path,
    }
    state.findings = list(findings)
    state.phase = "judged"
    return state


# ---------------------------------------------------------------------------
# SP4.2 — compute_convergence
# ---------------------------------------------------------------------------


def compute_convergence(
    concept_verdict: Verdict,
    user_verdict: Verdict,
    *,
    threshold: float = 4.0,
) -> bool:
    """Return True iff BOTH verdicts satisfy the convergence criteria.

    Convergence requires ALL of the following to hold:
    1. concept_verdict.overall_score >= threshold
    2. user_verdict.overall_score >= threshold
    3. concept_verdict.verdict != "blocked"
    4. user_verdict.verdict != "blocked"

    The weakest-link rule (embedded in each judge) means overall_score already
    reflects the lowest gating dimension, so checking overall_score is
    sufficient — no need to re-inspect individual dimensions here.

    claim_reality_coherence is advisory and excluded upstream from the judge's
    overall_score, so it does not appear here.

    Parameters
    ----------
    concept_verdict:
        Verdict from the ddd-concept-eval judge.
    user_verdict:
        Verdict from the user-artifact judge.
    threshold:
        Minimum overall_score required for both verdicts.  Default: 4.0.

    Returns
    -------
    bool
        True iff convergence criteria are satisfied; False otherwise.
    """
    if concept_verdict.verdict == "blocked" or user_verdict.verdict == "blocked":
        return False
    if concept_verdict.overall_score < threshold:
        return False
    if user_verdict.overall_score < threshold:
        return False
    return True
