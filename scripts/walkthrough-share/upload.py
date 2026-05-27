#!/usr/bin/env python3
"""Upload a walkthrough (.html or .mp4) to a canopy-web instance.

Used by /canopy:walkthrough-share. Stdlib only — no external deps.

Flow:
  1. Resolve config (api URL, PAT).
  2. For HTML: inline relative image/CSS refs as base64 data URIs.
  3. POST /api/walkthroughs/ multipart with Authorization: Bearer <PAT>.
  4. Print the view URL and (optionally) the share URL.

Auth: canopy-web's PersonalToken (PAT) at ~/.claude/canopy/workbench-token.
Mint with /canopy:canopy-web-pat-mint. Replaces the dead e2e-login flow.

Exits non-zero on any failure. Designed to be friendly to a SKILL.md
caller that just shells out and reads stdout.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_API = "https://canopy-web-ujpz2cuyxq-uc.a.run.app"
TOKEN_FILE = Path.home() / ".claude" / "canopy" / "workbench-token"

# Recognized file kinds and their server-side content types.
KIND_BY_EXT = {".html": "html", ".htm": "html", ".mp4": "video"}
CONTENT_TYPE_BY_KIND = {"html": "text/html", "video": "video/mp4"}


def fail(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def _describe_error(body: dict) -> str:
    """Render a Ninja problem+json error body into a readable one-liner.

    Falls back to {"error": ...} (legacy DRF) and raw-dict for defense.
    """
    if not isinstance(body, dict):
        return str(body)
    detail = body.get("detail")
    title = body.get("title")
    if detail and title:
        return f"{title}: {detail}"
    return detail or title or body.get("error") or str(body)


def resolve_pat() -> str:
    """Read the PAT from env or the canopy workbench-token file."""
    token = os.environ.get("CANOPY_WEB_PAT", "").strip()
    if token:
        return token
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        if token:
            return token
    fail(
        f"no canopy-web PAT — run /canopy:canopy-web-pat-mint to mint one, "
        f"or set CANOPY_WEB_PAT env var. Expected token at {TOKEN_FILE}.",
    )
    raise SystemExit  # unreachable, helps the type checker


def detect_kind(path: Path) -> str:
    kind = KIND_BY_EXT.get(path.suffix.lower())
    if kind is None:
        fail(
            f"unsupported extension {path.suffix!r} — only .html, .htm, and "
            f".mp4 are accepted",
        )
    return kind  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# HTML asset inlining
# ---------------------------------------------------------------------------

_ATTR_RE = re.compile(
    r"""(\b(?:src|href|poster)\s*=\s*)(['"])([^'"]+?)(\2)""",
    re.IGNORECASE,
)
_CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^)'"]+?)\1\s*\)""", re.IGNORECASE)


def _looks_remote(ref: str) -> bool:
    if not ref:
        return True
    if ref.startswith(("#", "data:", "mailto:", "javascript:")):
        return True
    if "://" in ref:
        return True
    if ref.startswith("//"):
        return True
    return False


def _inline_one(base_dir: Path, ref: str) -> str | None:
    """Resolve a relative ref to a data URI, or return None to leave it alone."""
    if _looks_remote(ref):
        return None
    clean = ref.split("?", 1)[0].split("#", 1)[0]
    target = (base_dir / clean).resolve()
    try:
        # Defense: don't escape the base dir.
        target.relative_to(base_dir.resolve())
    except ValueError:
        return None
    if not target.is_file():
        return None
    mime, _ = mimetypes.guess_type(str(target))
    if not mime:
        mime = "application/octet-stream"
    data = base64.b64encode(target.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def inline_html(path: Path) -> bytes:
    """Return the HTML with relative src/href/poster + url(...) refs inlined."""
    src = path.read_text(encoding="utf-8")
    base_dir = path.parent

    def attr_sub(m: re.Match) -> str:
        prefix, quote, ref, _ = m.group(1), m.group(2), m.group(3), m.group(4)
        data_uri = _inline_one(base_dir, ref)
        if data_uri is None:
            return m.group(0)
        return f"{prefix}{quote}{data_uri}{quote}"

    def css_sub(m: re.Match) -> str:
        quote, ref = m.group(1), m.group(2)
        data_uri = _inline_one(base_dir, ref)
        if data_uri is None:
            return m.group(0)
        return f"url({quote}{data_uri}{quote})"

    out = _ATTR_RE.sub(attr_sub, src)
    out = _CSS_URL_RE.sub(css_sub, out)
    return out.encode("utf-8")


# ---------------------------------------------------------------------------
# Multipart POST with Bearer auth
# ---------------------------------------------------------------------------


def _build_multipart(
    fields: dict[str, str],
    file_field: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> tuple[bytes, str]:
    boundary = "----canopyshare" + base64.urlsafe_b64encode(os.urandom(9)).decode("ascii")
    crlf = b"\r\n"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(str(value).encode("utf-8"))
    parts.append(f"--{boundary}".encode())
    parts.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"'.encode()
    )
    parts.append(f"Content-Type: {content_type}".encode())
    parts.append(b"")
    body = crlf.join(parts) + crlf + file_bytes + crlf + f"--{boundary}--".encode() + crlf
    return body, f"multipart/form-data; boundary={boundary}"


def upload_multipart(
    url: str,
    pat: str,
    fields: dict[str, str],
    file_field: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
    timeout: int = 120,
) -> tuple[int, dict]:
    body, ct = _build_multipart(fields, file_field, filename, content_type, file_bytes)
    headers = {
        "Content-Type": ct,
        "Authorization": f"Bearer {pat}",
    }
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {"error": e.reason}
        return e.code, payload
    raw = resp.read()
    payload = json.loads(raw.decode("utf-8")) if raw else {}
    return resp.status, payload


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="canopy:walkthrough-share",
        description="Upload a walkthrough to canopy-web (auth via PAT).",
    )
    p.add_argument("path", help="Path to a .html, .htm, or .mp4 file")
    p.add_argument("--title", help="Walkthrough title (defaults to filename stem)")
    p.add_argument("--description", default="", help="Optional description")
    p.add_argument("--project", dest="project_slug", help="Optional project slug")
    p.add_argument(
        "--public",
        action="store_true",
        help="Set visibility=link and print the share URL",
    )
    p.add_argument(
        "--api-url", default=os.environ.get("CANOPY_WEB_API_URL", DEFAULT_API),
        help="canopy-web base URL (default: %(default)s)",
    )
    args = p.parse_args(argv)

    src = Path(args.path).expanduser().resolve()
    if not src.is_file():
        fail(f"file not found: {src}")
    kind = detect_kind(src)
    content_type = CONTENT_TYPE_BY_KIND[kind]

    pat = resolve_pat()
    api = args.api_url.rstrip("/")
    title = (args.title or src.stem).strip()
    visibility = "link" if args.public else "private"

    if kind == "html":
        print(f"inlining HTML assets from {src.parent}…", file=sys.stderr)
        payload_bytes = inline_html(src)
    else:
        payload_bytes = src.read_bytes()
    upload_name = "slideshow.html" if kind == "html" else "video.mp4"

    size_mb = len(payload_bytes) / (1024 * 1024)
    print(f"uploading {size_mb:.1f} MB to {api}…", file=sys.stderr)

    fields = {
        "title": title,
        "kind": kind,
        "description": args.description,
        "visibility": visibility,
    }
    if args.project_slug:
        fields["project_slug"] = args.project_slug

    status, body = upload_multipart(
        f"{api}/api/walkthroughs/",
        pat=pat,
        fields=fields,
        file_field="file",
        filename=upload_name,
        content_type=content_type,
        file_bytes=payload_bytes,
    )
    if status != 201:
        fail(f"upload failed (HTTP {status}): {_describe_error(body)}")

    # canopy-web migrated DRF → Django Ninja in May 2026 — responses are bare
    # typed payloads (no {success, data, timing_ms} envelope). Read fields
    # directly off `body`.
    wid = body.get("id")
    if not wid:
        fail(f"unexpected response: {body}")

    # The /w/ viewer lives at the same host as the API base.
    print(f"View: {api}/w/{wid}")
    share_token = body.get("share_token")
    if visibility == "link" and share_token:
        print(f"Share: {api}/w/{wid}?t={share_token}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
