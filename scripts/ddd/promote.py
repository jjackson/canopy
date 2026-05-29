"""DDD promotion step — SP7.

Builds a self-contained documentation HTML page (hero video + capabilities +
why + how) from a converged run's unified_spec and why_brief, then publishes it
via canopy-web after passing the external_release review gate.

Public API
----------
build_docs_page(spec, why_brief, video_url) -> str
    Return a self-contained HTML string for the docs page.

publish_artifact(content, *, kind, title, base_url, token, _post) -> str
    Upload HTML or video to canopy-web and return the hosted URL.

promote(run_id, *, video_path, base_url, token, _upload, _gate, auto_approve_for_test) -> str
    Orchestrate: load state + spec + why_brief → upload video → build docs →
    external_release gate → upload HTML → save phase=promoted → return docs_url.

Notes
-----
- ``kind`` ∈ ``"html"`` | ``"video"``.
- HTML uploads go to ``/api/walkthroughs/`` (same endpoint as walkthrough-share).
- The gate is wired as ``_gate(review_request, base_url, token) -> str`` where the
  return value is the chosen option string (e.g. ``"publish"`` or ``"hold"``).
- No real network calls, no sleeping in production code — inject ``_post`` /
  ``_gate`` / ``_upload`` in tests.
"""
from __future__ import annotations

import base64
import html
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import yaml

from scripts.ddd.schemas.models import Decision, ReviewRequest, RunState, UnifiedSpec, WhyBrief
from scripts.ddd.runstate import load as load_state
from scripts.ddd.runstate import save as save_state
from scripts.ddd.runstate import _resolve_ddd_dir

DEFAULT_API = "https://canopy-web-ujpz2cuyxq-uc.a.run.app"
TOKEN_FILE = Path.home() / ".claude" / "canopy" / "workbench-token"

# ---------------------------------------------------------------------------
# Auth / URL resolution — mirrors review.py exactly
# ---------------------------------------------------------------------------


def _resolve_base_url(base_url: str | None) -> str:
    if base_url:
        return base_url.rstrip("/")
    from_env = os.environ.get("CANOPY_WEB_API_URL", "").strip()
    if from_env:
        return from_env.rstrip("/")
    return DEFAULT_API


def _resolve_token(token: str | None) -> str:
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
# CSS for the docs page — dark-mode shadcn-style tokens, no external deps
# ---------------------------------------------------------------------------

_DOCS_CSS = """
:root {
  --background: #0a0a0a;
  --foreground: #fafafa;
  --card: #111111;
  --card-foreground: #fafafa;
  --muted: #171717;
  --muted-foreground: #a1a1aa;
  --border: #262626;
  --primary: #fafafa;
  --accent: #262626;
  --accent-foreground: #fafafa;
  --success: #10b981;
  --info: #60a5fa;
  --warning: #f59e0b;
  --radius: 10px;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html { background: var(--background); scroll-behavior: smooth; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  color: var(--foreground);
  background: var(--background);
  -webkit-font-smoothing: antialiased;
}

a { color: var(--info); text-decoration: none; }
a:hover { text-decoration: underline; }

/* Layout */
.page-wrap {
  max-width: 860px;
  margin: 0 auto;
  padding: 0 1.5rem 6rem;
}

/* Hero */
.hero {
  padding: 3rem 0 2rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 2.5rem;
}

.hero-label {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted-foreground);
  margin-bottom: 0.5rem;
}

.hero h1 {
  font-size: 2.5rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--foreground);
  line-height: 1.15;
  margin-bottom: 1rem;
}

.hero-lede {
  font-size: 1.05rem;
  line-height: 1.6;
  color: var(--muted-foreground);
  margin-top: 0.5rem;
  max-width: 70ch;
}

.hero-video-wrap {
  margin-top: 2rem;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--border);
  background: #000;
}

.hero-video-wrap video,
.hero-video-wrap iframe {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  border: none;
}

/* Section titles */
h2 {
  font-size: 1.375rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--foreground);
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--border);
}

section {
  margin-bottom: 2.5rem;
}

/* Capability list */
.capability-list {
  list-style: none;
  padding: 0;
}

.capability-list li {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--border);
  color: var(--foreground);
  font-size: 0.975rem;
  line-height: 1.5;
}

.capability-list li:last-child { border-bottom: none; }

.cap-icon {
  flex-shrink: 0;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: var(--success);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 0.1rem;
  font-size: 0.7rem;
  color: #fff;
  font-weight: 700;
}

/* Why section */
.why-problem {
  background: var(--muted);
  border-left: 3px solid var(--info);
  border-radius: 0 var(--radius) var(--radius) 0;
  padding: 1rem 1.25rem;
  margin-bottom: 1.5rem;
  color: var(--muted-foreground);
  font-size: 0.975rem;
  line-height: 1.6;
}

.spine-item {
  padding: 1rem 0;
  border-bottom: 1px solid var(--border);
}

.spine-item:last-child { border-bottom: none; }

.spine-claim {
  font-weight: 600;
  color: var(--foreground);
  margin-bottom: 0.35rem;
  font-size: 0.975rem;
}

.spine-rationale {
  color: var(--muted-foreground);
  font-size: 0.9rem;
  line-height: 1.55;
}

/* How to use */
.how-list {
  list-style: none;
  padding: 0;
  counter-reset: step-counter;
}

.how-list li {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 0.85rem 0;
  border-bottom: 1px solid var(--border);
  counter-increment: step-counter;
}

.how-list li:last-child { border-bottom: none; }

.step-num {
  flex-shrink: 0;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 50%;
  background: var(--accent);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--muted-foreground);
  margin-top: 0.05rem;
}

.step-body {
  color: var(--foreground);
  font-size: 0.975rem;
  line-height: 1.55;
}

/* Footer */
.page-footer {
  margin-top: 3rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border);
  font-size: 0.8rem;
  color: var(--muted-foreground);
  text-align: center;
}
"""


# ---------------------------------------------------------------------------
# build_docs_page
# ---------------------------------------------------------------------------


def build_docs_page(spec: UnifiedSpec, why_brief: WhyBrief, video_url: str, poster_url: str = "") -> str:
    """Return a self-contained HTML documentation page.

    Structure
    ---------
    - Hero: title + hero video (``video_url``).
    - "What you can do": each scene's ``concept_claim``.
    - "Why it works this way": ``why_brief.problem`` + each ``spine`` item.
    - "How to use it": each scene's ``show``, in scene order.

    All user-supplied text is HTML-escaped — no XSS via concept_claim, show,
    rationale, or problem strings.

    Parameters
    ----------
    spec:
        The run's ``UnifiedSpec``.
    why_brief:
        The run's ``WhyBrief``.
    video_url:
        URL (HTTP/HTTPS or ``data:`` URI) of the hero video to embed.

    Returns
    -------
    str
        A complete, self-contained HTML document.
    """
    feature_name = html.escape(spec.name or why_brief.feature)
    esc_video_url = html.escape(video_url, quote=True)
    esc_poster = html.escape(poster_url, quote=True) if poster_url else ""
    # One-line lede: a docs page needs a crisp, plain-language hook (what it is + who
    # it's for), NOT the build-audience narrative. Prefer spec.tagline; fall back to the
    # narrative's first sentence only when no tagline is authored.
    tagline = (getattr(spec, "tagline", "") or "").strip()
    if tagline:
        narrative_lede = html.escape(tagline)
    else:
        _narr = (spec.narrative or "").strip()
        _first = re.split(r"(?<=\.)\s+", _narr, maxsplit=1)[0] if _narr else ""
        narrative_lede = html.escape(_first)

    # Determine if this is a remote URL or embeddable src — always use <video>
    # for .mp4 / data URIs; use <iframe> for http(s) links that look like
    # streaming share pages (e.g. canopy-web /w/ viewer).
    is_share_page = (
        video_url.startswith("http://") or video_url.startswith("https://")
    ) and "/w/" in video_url

    if is_share_page:
        video_html = (
            f'<iframe src="{esc_video_url}" allowfullscreen title="Feature demo"></iframe>'
        )
    else:
        poster_attr = f' poster="{esc_poster}"' if esc_poster else ""
        video_html = (
            f'<video controls preload="auto"{poster_attr} src="{esc_video_url}">'
            f'<a href="{esc_video_url}">Watch the demo video</a>'
            f"</video>"
        )

    # --- What you can do ---
    cap_items = ""
    for i, scene in enumerate(spec.scenes, 1):
        claim = html.escape(scene.concept_claim)
        cap_items += (
            f'<li><span class="cap-icon">&#10003;</span>'
            f'<span>{claim}</span></li>\n'
        )

    capabilities_section = f"""<section id="capabilities">
<h2>What you can do</h2>
<ul class="capability-list">
{cap_items}</ul>
</section>"""

    # --- Get started (user-facing adoption steps) ---
    getting_started = getattr(spec, "getting_started", []) or []
    if getting_started:
        gs_items = "".join(
            f'<li><span class="step-num">{i}</span>'
            f'<span class="step-body">{html.escape(step)}</span></li>\n'
            for i, step in enumerate(getting_started, 1)
        )
        getting_started_section = f"""<section id="get-started">
<h2>Get started</h2>
<ol class="how-list">
{gs_items}</ol>
</section>"""
    else:
        getting_started_section = ""

    # --- Why it works this way ---
    problem_esc = html.escape(why_brief.problem)
    spine_html = ""
    for item in why_brief.spine:
        claim_esc = html.escape(item.claim)
        rationale_esc = html.escape(item.rationale)
        spine_html += (
            f'<div class="spine-item">'
            f'<p class="spine-claim">{claim_esc}</p>'
            f'<p class="spine-rationale">{rationale_esc}</p>'
            f"</div>\n"
        )

    why_section = f"""<section id="why">
<h2>Why it works this way</h2>
<div class="why-problem">{problem_esc}</div>
{spine_html}</section>"""

    # --- How to use it ---
    how_items = ""
    for i, scene in enumerate(spec.scenes, 1):
        show_esc = html.escape(scene.show)
        how_items += (
            f'<li><span class="step-num">{i}</span>'
            f'<span class="step-body">{show_esc}</span></li>\n'
        )

    how_section = f"""<section id="how">
<h2>What the demo walks through</h2>
<ol class="how-list">
{how_items}</ol>
</section>"""

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{feature_name}</title>
<style>{_DOCS_CSS}</style>
</head>
<body>
<div class="page-wrap">

<div class="hero">
  <p class="hero-label">Feature documentation</p>
  <h1>{feature_name}</h1>
  {f'<p class="hero-lede">{narrative_lede}</p>' if narrative_lede else ''}
  <div class="hero-video-wrap">
    {video_html}
  </div>
</div>

{capabilities_section}

{getting_started_section}

{why_section}

{how_section}

<footer class="page-footer">Generated by canopy demo-driven-development</footer>

</div>
</body>
</html>"""

    return page


# ---------------------------------------------------------------------------
# publish_artifact
# ---------------------------------------------------------------------------

# Content-type by kind
_CT_BY_KIND = {"html": "text/html", "video": "video/mp4"}
_FILENAME_BY_KIND = {"html": "docs.html", "video": "video.mp4"}


def _default_post(
    url: str,
    pat: str,
    fields: dict,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> dict:
    """Real HTTP multipart POST to canopy-web using stdlib urllib.

    Returns the parsed JSON response body.
    Raises ``RuntimeError`` on non-201 responses.
    """
    boundary = (
        "----canorypromote"
        + base64.urlsafe_b64encode(os.urandom(9)).decode("ascii")
    )
    crlf = b"\r\n"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(str(value).encode("utf-8"))
    parts.append(f"--{boundary}".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode()
    )
    parts.append(f"Content-Type: {content_type}".encode())
    parts.append(b"")
    body = crlf.join(parts) + crlf + file_bytes + crlf + f"--{boundary}--".encode() + crlf

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {pat}",
    }
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)

    try:
        resp = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {"error": exc.reason}
        raise RuntimeError(
            f"canopy-web upload failed (HTTP {exc.code}): {payload}"
        ) from exc

    raw = resp.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


def publish_artifact(
    content: str | bytes,
    *,
    kind: str,
    title: str,
    base_url: str | None = None,
    token: str | None = None,
    _post=None,
) -> str:
    """Upload *content* to canopy-web and return the hosted URL.

    Parameters
    ----------
    content:
        The artifact to upload.  ``str`` → encoded as UTF-8.  ``bytes`` → sent
        as-is.
    kind:
        ``"html"`` or ``"video"``.
    title:
        Human-readable title shown in the canopy-web UI.
    base_url:
        canopy-web API base URL.  Falls back to ``CANOPY_WEB_API_URL`` env var
        then ``DEFAULT_API``.
    token:
        Bearer PAT.  Falls back to ``CANOPY_WEB_PAT`` env var then
        ``~/.claude/canopy/workbench-token``.
    _post:
        Injected HTTP callable for testing.  Signature::

            _post(url, pat, fields, filename, content_type, file_bytes) -> dict

        Defaults to the real multipart POST implementation.

    Returns
    -------
    str
        The hosted view URL (e.g. ``https://canopy-web.../w/<id>``).
    """
    if kind not in _CT_BY_KIND:
        raise ValueError(f"kind must be 'html' or 'video', got {kind!r}")

    api = _resolve_base_url(base_url)
    pat = _resolve_token(token)
    file_bytes = content.encode("utf-8") if isinstance(content, str) else content
    filename = _FILENAME_BY_KIND[kind]
    content_type = _CT_BY_KIND[kind]

    fields = {
        "title": title,
        "kind": kind,
        "description": "",
        "visibility": "link",
    }

    post_fn = _post if _post is not None else _default_post
    body = post_fn(
        f"{api}/api/walkthroughs/",
        pat,
        fields,
        filename,
        content_type,
        file_bytes,
    )

    wid = body.get("id")
    if not wid:
        raise RuntimeError(f"canopy-web returned unexpected response: {body}")

    share_token = body.get("share_token")
    if share_token:
        return f"{api}/w/{wid}?t={share_token}"
    return f"{api}/w/{wid}"


# ---------------------------------------------------------------------------
# _default_gate — wraps review.post_review_request + await_resolution
# ---------------------------------------------------------------------------


def _default_gate(review_request: ReviewRequest, base_url: str | None, token: str | None) -> str:
    """Post the review and block until resolved; return the chosen option.

    The resolved ``response_json`` must be a dict mapping decision id → chosen
    option string, e.g. ``{"publish": "publish"}``.  We look up the ``"publish"``
    decision and return its value.
    """
    from scripts.ddd import review as rv

    result = rv.post_review_request(
        review_request,
        visibility="link",
        base_url=base_url,
        token=token,
    )
    review_id = result["id"]
    response_json = rv.await_resolution(review_id, base_url=base_url, token=token)
    # response_json is the raw resolved response dict; the convention is
    # {decision_id: chosen_option} — find the first decision's value.
    if isinstance(response_json, dict):
        for decision in review_request.decisions:
            if decision.id in response_json:
                return str(response_json[decision.id])
    # Fallback: if the server returned a simple string or unexpected shape, hold
    return "hold"


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------


def promote(
    run_id: str,
    *,
    video_path: str,
    base_url: str | None = None,
    token: str | None = None,
    _upload: Callable = None,  # type: ignore[assignment]
    _gate: Callable = None,  # type: ignore[assignment]
    auto_approve_for_test: bool = False,
) -> str:
    """Promote a converged run to a published documentation page.

    Orchestration
    -------------
    1. Load ``run_state.yaml`` for *run_id*.
    2. Load ``unified_spec.yaml`` and ``why_brief.yaml`` from the run directory.
    3. Upload the hero video (*video_path*) via ``_upload(..., kind="video")``.
    4. Build the docs HTML via ``build_docs_page``.
    5. Run the **external_release gate** — construct a ``ReviewRequest`` and
       call ``_gate(review_request, base_url, token)``.
    6. If the human chose ``"hold"``: return ``""`` without uploading HTML.
       Phase stays unchanged.
    7. If ``"publish"``: upload the HTML via ``_upload(..., kind="html")``,
       set ``run_state.phase = "promoted"``, save, return *docs_url*.

    Parameters
    ----------
    run_id:
        Identifies the run under ``<ddd_dir>/runs/<run_id>/``.
    video_path:
        Path to the hero video ``.mp4`` on disk.
    base_url:
        Forwarded to ``_upload`` and ``_gate``.
    token:
        Forwarded to ``_upload`` and ``_gate``.
    _upload:
        Injected uploader callable for tests.  Defaults to ``publish_artifact``.
        Signature: ``(content, *, kind, title, base_url, token) -> str``.
    _gate:
        Injected gate callable for tests.
        Signature: ``(review_request, base_url, token) -> str`` (returns
        chosen option: ``"publish"`` or ``"hold"``).
        Defaults to ``_default_gate``.
    auto_approve_for_test:
        If ``True``, skip the gate and proceed directly to publish.  Only
        intended for integration tests that cannot mock ``_gate``.

    Returns
    -------
    str
        The hosted docs URL on publish, or ``""`` if the gate returned ``"hold"``.
    """
    upload_fn = _upload if _upload is not None else publish_artifact
    gate_fn = _gate if _gate is not None else _default_gate

    # 1. Load run state
    run_state = load_state(run_id)
    ddd_dir = _resolve_ddd_dir()
    run_dir = ddd_dir / "runs" / run_id

    # 2. Load spec + why_brief
    spec_path = run_dir / "unified_spec.yaml"
    why_brief_path = run_dir / "why_brief.yaml"

    raw_spec = yaml.safe_load(spec_path.read_text())
    spec = UnifiedSpec.model_validate(raw_spec)

    raw_why = yaml.safe_load(why_brief_path.read_text())
    why_brief = WhyBrief.model_validate(raw_why)

    # 3. Upload the hero video
    video_bytes = Path(video_path).read_bytes()
    video_url = upload_fn(
        video_bytes,
        kind="video",
        title=f"{spec.name} — hero video",
        base_url=base_url,
        token=token,
    )

    # 4. Build docs HTML
    html_content = build_docs_page(spec, why_brief, video_url)

    # 5. External release gate
    if not auto_approve_for_test:
        review_request = ReviewRequest(
            run_id=run_id,
            gate="external_release",
            video={"url": video_url},
            decisions=[
                Decision(
                    id="publish",
                    prompt="Publish this docs page for users?",
                    options=["publish", "hold"],
                    recommended="publish",
                    **{"class": "external_release"},
                )
            ],
            narration=[{"text": f"Docs page ready for {spec.name}. Review above video and approve to publish."}],
        )
        chosen = gate_fn(review_request, base_url, token)
        if chosen != "publish":
            # Human chose to hold — do not publish
            return ""

    # 6. Upload the docs HTML
    docs_url = upload_fn(
        html_content,
        kind="html",
        title=f"{spec.name} — documentation",
        base_url=base_url,
        token=token,
    )

    # 7. Update run state
    run_state.phase = "promoted"
    save_state(run_state)

    return docs_url


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="scripts.ddd.promote",
        description="Promote a converged DDD run to a published docs page.",
    )
    parser.add_argument("run_id", help="Run identifier (e.g. my-feature-2026-01-01-001)")
    parser.add_argument("--video", required=True, dest="video_path", help="Path to hero video .mp4")
    parser.add_argument("--base-url", default=None, help="canopy-web API base URL")
    args = parser.parse_args(argv)

    docs_url = promote(args.run_id, video_path=args.video_path, base_url=args.base_url)
    if docs_url:
        print(f"Published: {docs_url}")
    else:
        print("Promotion held — docs page was not published.")


if __name__ == "__main__":
    main()
