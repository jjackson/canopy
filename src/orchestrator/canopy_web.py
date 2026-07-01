"""Shared canopy-web transport + auth — the one place PAT/base-url resolution
and HTTP live. stdlib urllib only (the canopy plugin has no `requests` dep)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

DEFAULT_API = "https://labs.connect.dimagi.com/canopy"
TOKEN_FILE = Path.home() / ".claude" / "canopy" / "workbench-token"

Transport = Callable[[str, str, dict, Optional[bytes]], "tuple[int, str]"]


class CanopyError(RuntimeError):
    """A non-2xx response from canopy-web."""


def resolve_base_url(base_url: Optional[str]) -> str:
    if base_url:
        return base_url.rstrip("/")
    from_env = os.environ.get("CANOPY_WEB_API_URL", "").strip()
    if from_env:
        return from_env.rstrip("/")
    return DEFAULT_API


# Product apps that canopy-web scopes to a workspace. A path like
# ``/api/walkthroughs/…`` is rewritten to ``/api/w/<ws>/walkthroughs/…`` when a
# workspace is active; unscoped apps (insights, sessions, system, me, …) are
# left alone. Mirrors WS_SCOPED_API_PREFIXES on the canopy-web frontend.
SCOPED_APPS = ("projects", "walkthroughs", "reviews", "shareouts", "ddd", "timeline")


def resolve_workspace(workspace: Optional[str]) -> Optional[str]:
    """The active canopy-web workspace slug, or None (→ flat routes → the org
    default). Precedence: explicit arg → env ``CANOPY_WEB_WORKSPACE`` → None.
    The DDD layer adds a per-repo config source on top of this (see
    ``scripts/ddd/auth.resolve_ddd_workspace``)."""
    if workspace:
        return workspace.strip() or None
    from_env = os.environ.get("CANOPY_WEB_WORKSPACE", "").strip()
    return from_env or None


def scoped_api_path(path: str, workspace: Optional[str] = None) -> str:
    """Rewrite a flat ``/api/<app>/…`` path to the tenant path
    ``/api/w/<ws>/<app>/…`` when a workspace is active and ``<app>`` is scoped.
    A no-op when there is no workspace, the path isn't under ``/api/``, or the
    app isn't workspace-scoped."""
    ws = resolve_workspace(workspace)
    if not ws or not path.startswith("/api/"):
        return path
    rest = path[len("/api"):]  # "/walkthroughs/…"
    app = rest.lstrip("/").split("/", 1)[0]
    if app not in SCOPED_APPS:
        return path
    return f"/api/w/{ws}{rest}"


def scoped_app_path(path: str, workspace: Optional[str] = None) -> str:
    """Rewrite a flat browser route (e.g. ``/ddd/<slug>/<run>``) to its tenant
    form ``/w/<ws>/ddd/<slug>/<run>`` when a workspace is active — so package /
    landing links a human clicks open in the right workspace. No-op when there
    is no workspace."""
    ws = resolve_workspace(workspace)
    if not ws or not path.startswith("/"):
        return path
    return f"/w/{ws}{path}"


def resolve_token(token: Optional[str]) -> str:
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
        f"or set CANOPY_WEB_PAT. Expected token at {TOKEN_FILE}."
    )


def urllib_transport(method: str, url: str, headers: dict, body: Optional[bytes]) -> "tuple[int, str]":
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def call(method: str, path: str, body=None, *,
         base_url: Optional[str] = None, token: Optional[str] = None,
         workspace: Optional[str] = None,
         transport: Optional[Transport] = None) -> dict:
    base = resolve_base_url(base_url)
    tok = resolve_token(token)
    path = scoped_api_path(path, workspace)  # → /api/w/<ws>/… when a workspace is active
    transport = transport or urllib_transport
    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    status, text = transport(method, base + path, headers, data)
    if not (200 <= status < 300):
        raise CanopyError(f"{method} {path} -> {status}: {text[:400]}")
    return json.loads(text) if text.strip() else {}
