"""Neutral narrative substrate.

Generic narrative / evidence-gap / eval / review-package Pydantic models that
are NOT specific to any one methodology. ``ddd`` orchestrates these the same
way other consumers (an ACE AI-video pipeline, ace-web) can: import the models
from here, or generate cross-language types from the published JSON Schema under
``scripts/narrative/schema/json/`` and invoke the validators via ``python -m``.

The DDD-only ``RunState`` (the converge lifecycle) intentionally stays in
``scripts.ddd.schemas.models``; everything generic lives here.
"""
