"""Regenerate the committed narrative JSON schemas from the Pydantic models.

The generic models live in ``scripts/narrative/models.py`` (the canonical
cross-repo contract); the DDD-only ``RunState`` lives in
``scripts/ddd/schemas/models.py``. Both are emitted into
``scripts/narrative/schema/json/``.

This is the entry point invoked by the ``regen-ddd-json-schemas`` pre-commit
hook (see ``.pre-commit-config.yaml``). It is also safe to run by hand:

    python scripts/ddd/regen_json_schemas.py

Why a dedicated script (not an inline ``python -c`` in the hook entry)?

* ``pre-commit`` runs hooks in an isolated venv it manages. The hook's venv
  only has the dependencies listed under ``additional_dependencies``; it does
  **not** know about the canopy repo unless we put the repo root on
  ``sys.path``. A standalone script can do that in a couple of lines; an
  inline ``-c`` cannot.
* It gives developers a discoverable entry point — "regen the schemas" is a
  thing you can do without remembering the hook plumbing.

The script delegates to ``scripts.ddd.validate.dump_json_schemas`` so the
source of truth for "how do we emit JSON Schemas" stays in one place.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sure the canopy repo root is on sys.path so ``scripts.ddd.validate``
# resolves even when this script is run by pre-commit's isolated venv (which
# has no idea where the canopy repo lives).
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ddd.validate import dump_json_schemas  # noqa: E402


def main() -> int:
    out_dir = REPO_ROOT / "scripts" / "narrative" / "schema" / "json"
    dump_json_schemas(out_dir=out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
