"""DDD Why-Brief structural QA (SP1.3).

Pure-python, no LLM.  Reuses scripts/ddd/validate.py plus extra structural rules.

Exposes:
    why_qa(brief_obj_or_path) -> Verdict

Rules checked:
    (a) problem must be non-empty / non-whitespace
    (b) every SpineItem.rationale must be non-empty / non-whitespace
    (c) every grounded SpineItem must have >=1 evidence with kind != 'assumed'
    (d) every Gap.claim_ref must resolve to a SpineItem.id

Returns the ``Verdict`` model from scripts/ddd/schemas/models.py.
``verdict="pass"`` when all rules pass; ``verdict="fail"`` with a
``blocking_reason`` listing every violation when any rule fires.

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


def why_qa(brief_obj_or_path: Union[WhyBrief, Path, str]) -> Verdict:
    """Run structural QA on a WhyBrief.

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
    """
    # ------------------------------------------------------------------ load
    if isinstance(brief_obj_or_path, WhyBrief):
        brief = brief_obj_or_path
    else:
        path = Path(brief_obj_or_path)
        text = path.read_text()
        if path.suffix.casefold() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
        brief = WhyBrief.model_validate(raw)

    # ---------------------------------------------------------------- checks
    violations: list[str] = []

    # (a) problem must be non-empty
    if not brief.problem.strip():
        violations.append("problem: must not be empty")

    # (b) every SpineItem.rationale must be non-empty
    for item in brief.spine:
        if not item.rationale.strip():
            violations.append(
                f"SpineItem '{item.id}': rationale must not be empty"
            )

    # (c) grounded items must have >=1 non-assumed evidence
    for item in brief.spine:
        if item.status == "grounded":
            real = [e for e in item.evidence if e.kind != "assumed"]
            if not real:
                violations.append(
                    f"SpineItem '{item.id}': marked grounded but has no "
                    "non-assumed evidence (documented or implemented required)"
                )

    # (d) Gap.claim_ref must resolve to a SpineItem.id
    spine_ids = {item.id for item in brief.spine}
    for gap in brief.gaps:
        if gap.claim_ref not in spine_ids:
            violations.append(
                f"Gap '{gap.id}': claim_ref '{gap.claim_ref}' does not match "
                "any SpineItem.id"
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
            "pointer."
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
    try:
        _result = why_qa(_path)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if _result.verdict == "pass":
        print("why_qa: pass")
        sys.exit(0)
    else:
        print(f"why_qa: fail")
        print(f"  blocking_reason: {_result.blocking_reason}")
        if _result.fix_recommendation:
            print(f"  fix_recommendation: {_result.fix_recommendation}")
        sys.exit(1)
