"""DDD Why-Brief structural QA (SP1.3).

Pure-python, no LLM.  Delegates structural + semantic rules to validate.py;
adds QA-specific empty-field checks.

Exposes:
    why_qa(brief_obj_or_path) -> Verdict

Rules checked:
    (via validate.py → _semantic_why_brief)
    (d) duplicate SpineItem.id is an error
    (c) grounded SpineItem must have >=1 evidence with kind != 'assumed'
    (e) every Gap.claim_ref must resolve to a SpineItem.id

    (QA-specific, not in validate.py)
    (a) problem must be non-empty / non-whitespace
    (b) every SpineItem.rationale must be non-empty / non-whitespace

Returns the ``Verdict`` model from scripts/ddd/schemas/models.py.
``verdict="pass"`` when all rules pass; ``verdict="fail"`` with a
``blocking_reason`` listing every violation when any rule fires.

On missing path or malformed/unloadable input, returns a ``fail`` Verdict
instead of raising — consistent with the ``-> Verdict`` contract.

CLI:
    python -m scripts.ddd.why_qa <path>   # exits 0 on pass, 1 on fail, 2 on usage error
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Union

import yaml

from scripts.ddd.schemas.models import Verdict, WhyBrief
from scripts.ddd.validate import validate


def why_qa(brief_obj_or_path: Union[WhyBrief, Path, str]) -> Verdict:
    """Run structural QA on a WhyBrief.

    Delegates structural + semantic rules to ``validate("why_brief", ...)``
    (which covers duplicate-spine-id, grounded-evidence, and claim_ref checks),
    then adds QA-specific empty-field checks (empty/whitespace ``problem`` and
    ``rationale`` fields) that validate does not enforce.

    Parameters
    ----------
    brief_obj_or_path:
        Either a ``WhyBrief`` instance, or a ``Path`` / string path to a
        YAML or JSON file containing a WhyBrief.

    Returns
    -------
    Verdict
        ``verdict="pass"`` if all structural rules pass.
        ``verdict="fail"`` with ``blocking_reason`` listing every violation.
        Never raises — missing files and parse/validation errors are returned
        as a ``fail`` Verdict.
    """
    # ------------------------------------------------------------------ load
    if isinstance(brief_obj_or_path, WhyBrief):
        brief = brief_obj_or_path
        # Run validate on the dict representation so we get its semantic checks
        _ok, _validate_problems = validate("why_brief", brief.model_dump())
    else:
        path = Path(brief_obj_or_path)
        if not path.exists():
            return Verdict(
                schema_version=1,
                dimensions={},
                overall_score=0.0,
                verdict="fail",
                blocking_reason=f"File not found: {path}",
                fix_recommendation="Provide a valid path to a why_brief YAML or JSON file.",
            )
        try:
            text = path.read_text()
            if path.suffix.casefold() == ".json":
                raw = json.loads(text)
            else:
                raw = yaml.safe_load(text)
            brief = WhyBrief.model_validate(raw)
        except Exception as exc:
            return Verdict(
                schema_version=1,
                dimensions={},
                overall_score=0.0,
                verdict="fail",
                blocking_reason=f"Could not load or parse why_brief: {exc}",
                fix_recommendation="Ensure the file is valid YAML/JSON conforming to the WhyBrief schema.",
            )
        _ok, _validate_problems = validate("why_brief", path)

    # ---------------------------------------------------------------- checks
    violations: list[str] = list(_validate_problems)  # delegate to validate.py

    # (a) problem must be non-empty (QA-specific)
    if not brief.problem.strip():
        violations.append("problem: must not be empty")

    # (b) every SpineItem.rationale must be non-empty (QA-specific)
    for item in brief.spine:
        if not item.rationale.strip():
            violations.append(
                f"SpineItem '{item.id}': rationale must not be empty"
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
            "Fix the listed structural violations before running ddd-why-eval. "
            "Each violation is a load-bearing rule: empty rationale leaves the "
            "spine claim unjustified; a grounded claim without real evidence is "
            "aspirational, not grounded; an unresolved claim_ref is a dangling "
            "pointer; duplicate spine ids break provenance tracing."
        ),
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "Usage: python -m scripts.ddd.why_qa <path>",
            file=sys.stderr,
        )
        sys.exit(2)

    _path = Path(sys.argv[1])
    _result = why_qa(_path)

    if _result.verdict == "pass":
        print("why_qa: pass")
        sys.exit(0)
    else:
        print(f"why_qa: fail")
        print(f"  blocking_reason: {_result.blocking_reason}")
        if _result.fix_recommendation:
            print(f"  fix_recommendation: {_result.fix_recommendation}")
        sys.exit(1)
