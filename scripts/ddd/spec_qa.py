"""DDD UnifiedSpec structural QA (SP2.2).

Pure-python, no LLM.  Delegates structural + semantic rules to validate.py;
adds QA-specific falsifiability checks on Scene.concept_claim.

Exposes:
    spec_qa(spec_obj_or_path) -> Verdict

Rules checked:
    (via validate.py → _semantic_unified_spec)
    (b) Scene.provenance must match a SpineItem.id in the linked why_brief
    (e) Scene.persona must be defined in the personas dict
    (f) why_brief declared but not resolvable → problem
    Plus Pydantic-required fields (name, narrative, base_url, personas, scenes)

    (QA-specific, not in validate.py)
    (g) every Scene.concept_claim must be non-empty / non-whitespace
    (h) every Scene.concept_claim must be falsifiable — fails if it matches
        a banned list of pure-marketing phrases, OR is too short to be specific.

Returns the ``Verdict`` model from scripts/ddd/schemas/models.py.
``verdict="pass"`` when all rules pass; ``verdict="fail"`` with a
``blocking_reason`` listing every violation when any rule fires.

On missing path, malformed input, or None, returns a ``fail`` Verdict
instead of raising — consistent with the ``-> Verdict`` contract.

CLI:
    python -m scripts.ddd.spec_qa <spec_path>
    exits 0 on pass, 1 on fail, 2 on usage error
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Union

import yaml

from scripts.ddd.schemas.models import UnifiedSpec, Verdict
from scripts.ddd.validate import validate

# ---------------------------------------------------------------------------
# Banned marketing phrases (case-insensitive substring match).
# If a concept_claim contains any of these, it is considered non-falsifiable.
# ---------------------------------------------------------------------------

_BANNED_PHRASES: list[str] = [
    "world-class",
    "world class",
    "seamless",
    "powerful",
    "robust",
    "best-in-class",
    "best in class",
    "cutting-edge",
    "cutting edge",
    "state-of-the-art",
    "state of the art",
    "revolutionary",
    "game-changing",
    "game changing",
    "innovative",
    "next-generation",
    "next generation",
]


def _is_falsifiable(claim: str) -> bool:
    """Return True if the claim is falsifiable (not vacuous marketing copy).

    A claim is NOT falsifiable if:
    1. It is empty or whitespace-only.
    2. It contains any banned marketing phrase.
    3. It is fewer than 5 words (too short to be specific).

    Verb-pattern detection has been intentionally removed.  It caused false
    positives (blocking legitimate nominalized claims like "GPS pinning accuracy
    within 5 meters" or "Per-stratum allocation proportional to population") and
    false negatives (accepting fluff containing a copula like "The system is
    good").  Subtle vacuousness judgment — distinguishing a real claim from an
    articulate-but-empty one — belongs to the LLM concept judge (SP3), not this
    binary structural gate.
    """
    stripped = claim.strip()
    if not stripped:
        return False

    # Check for banned phrases (case-insensitive)
    lower = stripped.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            return False

    # Minimum specificity: a falsifiable claim needs enough substance.
    # Subtle vacuousness is the LLM concept judge's job (SP3), not this regex gate.
    if len(stripped.split()) < 5:
        return False

    return True


def spec_qa(
    spec_obj_or_path: Any,
) -> Verdict:
    """Run structural QA on a UnifiedSpec.

    Delegates structural + semantic rules to ``validate("unified_spec", ...)``
    (which covers persona-defined, provenance-to-spine-id, and required-field
    checks), then adds QA-specific falsifiability checks on every
    ``Scene.concept_claim`` that ``validate`` does not enforce.

    The why_brief is resolved by validate() from the spec file's own
    ``why_brief`` field (relative to the spec file path) — no separate
    path argument is needed.

    Parameters
    ----------
    spec_obj_or_path:
        Either a ``UnifiedSpec`` instance, a ``Path`` / string path to a
        YAML or JSON file containing a UnifiedSpec, or a plain dict.

    Returns
    -------
    Verdict
        ``verdict="pass"`` if all structural rules pass.
        ``verdict="fail"`` with ``blocking_reason`` listing every violation.
        Never raises — missing files and parse/validation errors are returned
        as a ``fail`` Verdict.
    """
    # ------------------------------------------------------------------ guard
    if spec_obj_or_path is None:
        return Verdict(
            schema_version=1,
            dimensions={},
            overall_score=0.0,
            verdict="fail",
            blocking_reason="spec_obj_or_path is None",
            fix_recommendation="Provide a valid UnifiedSpec object or path.",
        )

    # -------------------------------------------------------------- delegate
    # validate() handles loading, Pydantic validation, persona check, and
    # provenance cross-check.  We collect its problems and add our own.
    _ok, _validate_problems = validate("unified_spec", spec_obj_or_path)
    violations: list[str] = list(_validate_problems)

    # ------------------------------------------------- load spec for QA checks
    # We need the parsed spec object to run QA-specific checks.
    # If validate() already failed on loading, we may not be able to parse.
    spec: UnifiedSpec | None = None

    if isinstance(spec_obj_or_path, UnifiedSpec):
        spec = spec_obj_or_path
    elif isinstance(spec_obj_or_path, (str, Path)):
        path = Path(spec_obj_or_path)
        if path.exists():
            try:
                text = path.read_text()
                if path.suffix.casefold() == ".json":
                    raw = json.loads(text)
                else:
                    raw = yaml.safe_load(text)
                from pydantic import ValidationError

                try:
                    spec = UnifiedSpec.model_validate(raw)
                except ValidationError:
                    spec = None  # structural errors already captured via validate()
            except Exception:
                spec = None  # loading errors already captured via validate()
        # else: file not found — validate() already captured the error
    elif isinstance(spec_obj_or_path, dict):
        try:
            spec = UnifiedSpec.model_validate(spec_obj_or_path)
        except Exception:
            spec = None

    # --------------------------------------------------- QA-specific checks
    if spec is not None:
        for scene in spec.scenes:
            claim = scene.concept_claim
            if not _is_falsifiable(claim):
                if not claim.strip():
                    violations.append(
                        f"scene '{scene.title}': concept_claim is empty — "
                        "must describe an observable, falsifiable outcome"
                    )
                else:
                    violations.append(
                        f"scene '{scene.title}': concept_claim is not falsifiable — "
                        f"'{claim[:80]}' uses marketing language or is too short (fewer than 5 words); "
                        "write a specific, observable outcome instead"
                    )

    # --------------------------------------------------------------- verdict
    if not violations:
        return Verdict(
            schema_version=1,
            dimensions={},
            overall_score=1.0,
            verdict="pass",
            blocking_reason=None,
            fix_recommendation=None,
        )

    blocking_reason = "; ".join(violations)
    return Verdict(
        schema_version=1,
        dimensions={},
        overall_score=0.0,
        verdict="fail",
        blocking_reason=blocking_reason,
        fix_recommendation=(
            "Fix the listed violations before running the concept judge. "
            "Each concept_claim must describe a specific, observable, falsifiable "
            "outcome — e.g. 'Users can filter the task list by status and see only "
            "open tasks' not 'a world-class seamless experience'. "
            "Persona must be defined in the personas dict. "
            "Provenance must match a SpineItem.id in the linked why_brief. "
            "All required fields (name, narrative, base_url, personas, scenes) must be present."
        ),
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "Usage: python -m scripts.ddd.spec_qa <spec_path>",
            file=sys.stderr,
        )
        sys.exit(2)

    _spec_path = sys.argv[1]

    _result = spec_qa(_spec_path)

    if _result.verdict == "pass":
        print("spec_qa: pass")
        sys.exit(0)
    else:
        print("spec_qa: fail")
        print(f"  blocking_reason: {_result.blocking_reason}")
        if _result.fix_recommendation:
            print(f"  fix_recommendation: {_result.fix_recommendation}")
        sys.exit(1)
