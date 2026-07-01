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
from pathlib import Path
from typing import Optional

from orchestrator.canopy_web import (  # noqa: F401  (re-exported public API)
    DEFAULT_API,
    TOKEN_FILE,
    resolve_base_url,
    resolve_token,
    resolve_workspace,
    scoped_api_path,
    scoped_app_path,
)


def resolve_ddd_workspace(
    workspace: Optional[str] = None, *, ddd_dir: Optional[Path] = None
) -> Optional[str]:
    """The canopy-web workspace a DDD run targets, or None (→ flat routes → the
    org default, e.g. ``dimagi``).

    Precedence: explicit arg → env ``CANOPY_WEB_WORKSPACE`` → per-repo
    ``<repo>/.canopy/ddd/config.yaml`` (``workspace:`` key) → None. The per-repo
    file is how a repo pins its DDD artifacts to a workspace (e.g. the Connect
    repo commits ``workspace: connect``) without anyone remembering an env var.
    """
    ws = resolve_workspace(workspace)  # explicit arg → env → None
    if ws:
        return ws
    try:
        import yaml

        from scripts.ddd.runstate import _resolve_ddd_dir

        d = Path(ddd_dir) if ddd_dir is not None else _resolve_ddd_dir()
        cfg = d / "config.yaml"
        if cfg.exists():
            data = yaml.safe_load(cfg.read_text()) or {}
            val = str(data.get("workspace") or "").strip()
            return val or None
    except Exception:
        return None
    return None


__all__ = [
    "DEFAULT_API",
    "TOKEN_FILE",
    "resolve_base_url",
    "resolve_token",
    "resolve_workspace",
    "resolve_ddd_workspace",
    "scoped_api_path",
    "scoped_app_path",
]
