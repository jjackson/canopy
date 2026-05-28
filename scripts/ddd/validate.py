"""DDD artifact validator (SP0.3).

Exposes:
  validate(kind, obj_or_path) -> tuple[bool, list[str]]

  dump_json_schemas(out_dir="scripts/ddd/schemas/json") -> None

CLI:
  python -m scripts.ddd.validate <kind> <path>   # exits 0 on valid, 1 on invalid

Supported kinds: why_brief, unified_spec, verdict, review_request, run_state
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from scripts.ddd.schemas.models import (
    Decision,
    ReviewRequest,
    RunState,
    UnifiedSpec,
    Verdict,
    WhyBrief,
)

_MODEL_MAP = {
    "why_brief": WhyBrief,
    "unified_spec": UnifiedSpec,
    "verdict": Verdict,
    "review_request": ReviewRequest,
    "run_state": RunState,
}


def _load(path: Path) -> Any:
    """Load YAML or JSON from *path*."""
    text = path.read_text()
    if path.suffix in {".json"}:
        return json.loads(text)
    return yaml.safe_load(text)


def _semantic_why_brief(obj: WhyBrief) -> list[str]:
    """Semantic rules for WhyBrief.

    (a) grounded SpineItem must have ≥1 evidence with kind != 'assumed'
    (c) every Gap.claim_ref must resolve to a SpineItem.id
    """
    problems: list[str] = []
    spine_ids = {s.id for s in obj.spine}

    for item in obj.spine:
        if item.status == "grounded":
            real = [e for e in item.evidence if e.kind != "assumed"]
            if not real:
                problems.append(
                    f"SpineItem '{item.id}' is grounded but has no non-assumed evidence."
                )

    for gap in obj.gaps:
        if gap.claim_ref not in spine_ids:
            problems.append(
                f"Gap '{gap.id}' has claim_ref '{gap.claim_ref}' "
                f"which does not match any SpineItem.id."
            )

    return problems


def _semantic_unified_spec(obj: UnifiedSpec, spec_path: Path | None) -> list[str]:
    """Semantic rules for UnifiedSpec.

    (b) when a why_brief is resolvable (relative to spec file), every
        Scene.provenance must match some SpineItem.id
    """
    problems: list[str] = []

    if obj.why_brief and spec_path is not None:
        wb_path = spec_path.parent / obj.why_brief
        if wb_path.exists():
            try:
                wb_data = _load(wb_path)
                wb = WhyBrief.model_validate(wb_data)
                spine_ids = {s.id for s in wb.spine}
                for scene in obj.scenes:
                    if scene.provenance not in spine_ids:
                        problems.append(
                            f"Scene '{scene.title}' has provenance '{scene.provenance}' "
                            f"which does not match any SpineItem.id in the why_brief."
                        )
            except (ValidationError, Exception):
                # If the why_brief itself is invalid, skip provenance check
                pass

    return problems


def validate(
    kind: str,
    obj_or_path: Any,
) -> tuple[bool, list[str]]:
    """Validate an artifact of *kind*.

    Parameters
    ----------
    kind:
        One of: why_brief, unified_spec, verdict, review_request, run_state
    obj_or_path:
        Either a ``Path`` / path-like to a YAML/JSON file, or a plain dict.

    Returns
    -------
    (ok, problems)
        ok=True means the artifact is structurally and semantically valid.
        problems is an empty list when ok=True, otherwise a list of strings.
    """
    if kind not in _MODEL_MAP:
        return False, [f"Unknown kind '{kind}'. Choose from {list(_MODEL_MAP)}."]

    model_cls = _MODEL_MAP[kind]
    spec_path: Path | None = None

    # Load if given a path
    if isinstance(obj_or_path, (str, Path)):
        spec_path = Path(obj_or_path)
        try:
            raw = _load(spec_path)
        except Exception as exc:
            return False, [f"Failed to load file: {exc}"]
    else:
        raw = obj_or_path

    # Structural validation via Pydantic
    try:
        obj = model_cls.model_validate(raw)
    except ValidationError as exc:
        problems = [str(e) for e in exc.errors()]
        return False, problems

    # Semantic validation
    problems: list[str] = []
    if kind == "why_brief":
        problems = _semantic_why_brief(obj)  # type: ignore[arg-type]
    elif kind == "unified_spec":
        problems = _semantic_unified_spec(obj, spec_path)  # type: ignore[arg-type]

    return (len(problems) == 0), problems


def dump_json_schemas(out_dir: str | Path = "scripts/ddd/schemas/json") -> None:
    """Write JSON Schema files for every DDD model into *out_dir*."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    all_models = [
        WhyBrief,
        UnifiedSpec,
        Verdict,
        Decision,
        ReviewRequest,
        RunState,
    ]
    for model in all_models:
        schema = model.model_json_schema()
        dest = out / f"{model.__name__}.json"
        dest.write_text(json.dumps(schema, indent=2))
        print(f"Wrote {dest}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: python -m scripts.ddd.validate <kind> <path>", file=sys.stderr)
        sys.exit(2)

    _kind = sys.argv[1]
    _path = sys.argv[2]

    _ok, _problems = validate(_kind, _path)
    if _ok:
        print(f"Valid {_kind}.")
        sys.exit(0)
    else:
        print(f"Invalid {_kind}:")
        for p in _problems:
            print(f"  - {p}")
        sys.exit(1)
