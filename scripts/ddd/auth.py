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

import os
from pathlib import Path

DEFAULT_API = "https://canopy-web-ujpz2cuyxq-uc.a.run.app"
TOKEN_FILE = Path.home() / ".claude" / "canopy" / "workbench-token"


def resolve_base_url(base_url: str | None) -> str:
    """Return the effective base URL, stripped of trailing slash.

    Precedence: explicit ``base_url`` arg > ``CANOPY_WEB_API_URL`` env >
    :data:`DEFAULT_API`.
    """
    if base_url:
        return base_url.rstrip("/")
    from_env = os.environ.get("CANOPY_WEB_API_URL", "").strip()
    if from_env:
        return from_env.rstrip("/")
    return DEFAULT_API


def resolve_token(token: str | None) -> str:
    """Return the effective PAT, raising ``RuntimeError`` if unavailable.

    Precedence: explicit ``token`` arg > ``CANOPY_WEB_PAT`` env >
    :data:`TOKEN_FILE` on disk.
    """
    if token:
        return token
    from_env = os.environ.get("CANOPY_WEB_PAT", "").strip()
    if from_env:
        return from_env
    if TOKEN_FILE.exists():
        stored = TOKEN_FILE.read_text().strip()
        if stored:
            return stored
    raise RuntimeError(
        f"no canopy-web PAT — run /canopy:canopy-web-pat-mint to mint one, "
        f"or set CANOPY_WEB_PAT env var. Expected token at {TOKEN_FILE}."
    )
