"""Shared canopy-web auth + URL resolution for the DDD scripts.

Single source of truth for the conventions previously duplicated byte-for-byte
in ``scripts/ddd/review.py`` and ``scripts/ddd/upload.py``:

  - Base URL: env var ``CANOPY_WEB_API_URL``, default :data:`DEFAULT_API`.
  - PAT:      env var ``CANOPY_WEB_PAT``, then the on-disk :data:`TOKEN_FILE`.

Public API
----------
resolve_base_url(base_url: str | None) -> str
    Effective base URL, stripped of any trailing slash.
resolve_token(token: str | None) -> str
    Effective PAT; raises ``RuntimeError`` if none can be resolved.
"""
from __future__ import annotations

# Canonical single source of these conventions now lives in orchestrator.canopy_web;
# this module re-exports them so existing callers (scripts/ddd/upload.py, review.py) are
# untouched. Run under `uv run` from the repo root, where `orchestrator` is importable.
from orchestrator.canopy_web import (  # noqa: F401  (re-exported public API)
    DEFAULT_API,
    TOKEN_FILE,
    resolve_base_url,
    resolve_token,
)

__all__ = ["DEFAULT_API", "TOKEN_FILE", "resolve_base_url", "resolve_token"]
