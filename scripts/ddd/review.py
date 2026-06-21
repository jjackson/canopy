"""Canopy-side client for the canopy-web review surface (SP6c).

Mirrors the auth and URL-resolution conventions from
scripts/walkthrough-share/upload.py:
  - Base URL: env var CANOPY_WEB_API_URL, default DEFAULT_API
  - PAT:      env var CANOPY_WEB_PAT, then ~/.claude/canopy/workbench-token

HTTP transport: stdlib urllib (no requests dep — matches upload.py).
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from scripts.ddd.schemas.models import ReviewRequest
from scripts.ddd.auth import (
    DEFAULT_API,
    TOKEN_FILE,
    resolve_base_url as _resolve_base_url,
    resolve_token as _resolve_token,
)


# ---------------------------------------------------------------------------
# Narrative-review URL helpers — shared by upload.py and narrative.py
# ---------------------------------------------------------------------------


_REVIEW_ID_RE = re.compile(
    r"/review/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


def _review_id_from_url(url: str | None) -> str | None:
    """Extract the ReviewRequest UUID from a narrative-review URL
    (``.../review/<uuid>/?t=...``), or None."""
    if not url:
        return None
    m = _REVIEW_ID_RE.search(url)
    return m.group(1) if m else None


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


def resolve_review(
    review_id: str, response_json: dict, *, base_url: str | None = None, token: str | None = None
) -> dict:
    """Resolve a review gate by submitting the decision to canopy-web.

    POSTs to ``/api/reviews/<id>/submit/`` — the same endpoint the human review
    page submits to. It is Bearer-PAT authenticated, so the resolution is
    ATTRIBUTED to the token's user: the review is created AND marked resolved with
    ``response_json``, not bypassed, so the publish decision stays accountable.
    ``await_resolution`` then returns that ``response_json``.

    ``response_json`` is the ``{decision_id: chosen_option}`` map the gate expects,
    e.g. ``{"publish": "publish"}`` for the external_release gate.

    Use this to record an approval a human already gave out-of-band (an operator
    told the agent "publish it") WITHOUT forcing a UI click. The gate still pauses
    for a *decision*; this lets an authorized agent *record* a decision already made.
    """
    api = _resolve_base_url(base_url)
    tok = _resolve_token(token)
    return _json_request(
        "POST", f"{api}/api/reviews/{review_id}/submit/", tok, {"response_json": response_json}
    )
