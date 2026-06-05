"""Canopy-side client for the canopy-web review surface (SP6c).

Mirrors the auth and URL-resolution conventions from
scripts/walkthrough-share/upload.py:
  - Base URL: env var CANOPY_WEB_API_URL, default DEFAULT_API
  - PAT:      env var CANOPY_WEB_PAT, then ~/.claude/canopy/workbench-token

HTTP transport: stdlib urllib (no requests dep — matches upload.py).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from scripts.ddd.schemas.models import ReviewRequest

DEFAULT_API = "https://canopy-web-ujpz2cuyxq-uc.a.run.app"
TOKEN_FILE = Path.home() / ".claude" / "canopy" / "workbench-token"


# ---------------------------------------------------------------------------
# Auth / URL resolution — mirrors upload.py exactly
# ---------------------------------------------------------------------------


def _resolve_base_url(base_url: str | None) -> str:
    """Return the effective base URL, stripped of trailing slash."""
    if base_url:
        return base_url.rstrip("/")
    from_env = os.environ.get("CANOPY_WEB_API_URL", "").strip()
    if from_env:
        return from_env.rstrip("/")
    return DEFAULT_API


def _resolve_token(token: str | None) -> str:
    """Return the effective PAT, raising RuntimeError if unavailable."""
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


# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------


def _json_request(method: str, url: str, token: str, body: dict | None = None) -> dict:
    """Make a JSON request and return the parsed response body.

    Raises urllib.error.HTTPError on non-2xx responses.
    """
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError:
        raise
    raw = resp.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def post_review_request(
    review_request: ReviewRequest,
    *,
    visibility: str = "link",
    base_url: str | None = None,
    token: str | None = None,
) -> dict:
    """POST a ReviewRequest to the review surface.

    Serialises with ``model_dump(by_alias=True)`` so Decision objects emit
    the ``"class"`` key (alias) rather than ``class_`` (field name).

    Returns ``{id, url, share_token}`` from the server.
    """
    api = _resolve_base_url(base_url)
    tok = _resolve_token(token)
    payload = {
        "request_json": review_request.model_dump(by_alias=True),
        "visibility": visibility,
    }
    return _json_request("POST", f"{api}/api/reviews/", tok, payload)


def get_review(
    review_id: str,
    *,
    base_url: str | None = None,
    token: str | None = None,
) -> dict:
    """GET ``/api/reviews/<review_id>/``.

    Returns ``{request_json, response_json, status, is_owner, share_token, ...}``.
    """
    api = _resolve_base_url(base_url)
    tok = _resolve_token(token)
    return _json_request("GET", f"{api}/api/reviews/{review_id}/", tok)


def get_narrative(
    slug: str,
    *,
    base_url: str | None = None,
    token: str | None = None,
) -> dict | None:
    """GET ``/api/ddd/narratives/<slug>/`` — the narrative's versions + runs.

    Returns the narrative-detail dict, or ``None`` if no narrative exists for
    ``slug`` (HTTP 404). Any other HTTP error propagates.
    """
    import urllib.parse

    api = _resolve_base_url(base_url)
    tok = _resolve_token(token)
    quoted = urllib.parse.quote(slug, safe="")
    try:
        return _json_request("GET", f"{api}/api/ddd/narratives/{quoted}/", tok)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def narrative_version_exists(
    slug: str,
    *,
    base_url: str | None = None,
    token: str | None = None,
) -> bool:
    """Return True iff canopy-web has at least one *narrative version* for ``slug``.

    A narrative version is a story-bearing ``concept_change`` review — i.e. the
    ``ddd-narrative-review`` gate ran for this narrative. canopy-web surfaces it
    as a non-null ``current_version`` on the narrative detail. When this is
    False, a run under ``slug`` would render as **"no narrative"** in the UI, so
    ``ddd-upload`` refuses to publish it.
    """
    detail = get_narrative(slug, base_url=base_url, token=token)
    if not detail:
        return False
    if detail.get("current_version"):
        return True
    # Defensive: a version row carrying a real version number also counts, even
    # if current_version resolution lagged.
    return any(
        (v or {}).get("version") is not None for v in (detail.get("versions") or [])
    )


def await_resolution(
    review_id: str,
    *,
    poll_interval: float = 5.0,
    timeout: float = 86400.0,
    base_url: str | None = None,
    token: str | None = None,
    _sleep: object = time.sleep,
    _now: object = time.monotonic,
) -> dict:
    """Poll ``get_review`` until ``status == "resolved"``, then return ``response_json``.

    Parameters
    ----------
    review_id:
        The review ID to poll.
    poll_interval:
        Seconds to sleep between polls.
    timeout:
        Maximum wall-clock seconds to wait before raising ``TimeoutError``.
    base_url, token:
        Forwarded to ``get_review`` for resolution.
    _sleep, _now:
        Injected for testing (default: ``time.sleep`` / ``time.monotonic``).
        Pass a fake ``_now`` that advances a counter and a no-op ``_sleep``
        to drive the loop without real sleeping.
    """
    deadline = _now() + timeout  # type: ignore[operator]
    while True:
        data = get_review(review_id, base_url=base_url, token=token)
        if data.get("status") == "resolved":
            return data["response_json"]
        if _now() >= deadline:  # type: ignore[operator]
            raise TimeoutError(
                f"review {review_id!r} not resolved within {timeout}s"
            )
        _sleep(poll_interval)  # type: ignore[operator]
