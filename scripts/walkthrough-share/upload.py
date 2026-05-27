#!/usr/bin/env python3
"""Upload a walkthrough (.html or .mp4) to a canopy-web instance.

Used by /canopy:walkthrough-share. Stdlib only — no external deps.

Flow:
  1. Resolve config (api URL, email, upload token).
  2. For HTML: inline relative image refs as base64 data URIs.
  3. POST /api/auth/e2e-login/ → session cookie.
  4. POST /api/walkthroughs/ multipart (with session cookie).
  5. Print the view URL and (optionally) the share URL.

Exits non-zero on any failure. Designed to be friendly to a SKILL.md
caller that just shells out and reads stdout.
"""
from __future__ import annotations

import argparse
import base64
import http.cookiejar
import json
import mimetypes
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_API = "https://canopy-web-ujpz2cuyxq-uc.a.run.app"
TOKEN_FILE = Path.home() / ".claude" / "canopy" / "walkthrough-upload-token"
ALLOWED_DOMAIN = "dimagi.com"

# Recognized file kinds and their server-side content types.
KIND_BY_EXT = {".html": "html", ".htm": "html", ".mp4": "video"}
CONTENT_TYPE_BY_KIND = {"html": "text/html", "video": "video/mp4"}


def fail(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def _describe_error(body: dict) -> str:
    """Best-effort one-line render of a Ninja problem+json error body.

    Ninja errors look like {"type": "...", "title": "...", "status": N,
    "detail": "..."}; older DRF errors used {"error": "..."}. Fall through
    to the raw dict so callers always get something.
    """
    if not isinstance(body, dict):
        return str(body)
    detail = body.get("detail")
    title = body.get("title")
    if detail and title:
        return f"{title}: {detail}"
    return detail or title or body.get("error") or str(body)


def resolve_email(override: str | None) -> str:
    """Pick an email: --as flag → env → git config user.email."""
    if override:
        email = override.strip()
    else:
        email = os.environ.get("CANOPY_WALKTHROUGH_EMAIL", "").strip()
    if not email:
        try:
            out = subprocess.check_output(
                ["git", "config", "user.email"], text=True, stderr=subprocess.DEVNULL,
            )
            email = out.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    if not email:
        fail(
            "could not resolve email — pass --as <email>, set "
            "CANOPY_WALKTHROUGH_EMAIL, or configure git user.email",
        )
    if not email.endswith(f"@{ALLOWED_DOMAIN}"):
        fail(f"email {email!r} is not in the @{ALLOWED_DOMAIN} domain")
    return email


def resolve_token() -> str:
    """Read the upload token from env or the token file."""
    token = os.environ.get("CANOPY_E2E_AUTH_TOKEN", "").strip()
    if token:
        return token
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        if token:
            return token
    fail(
        f"no upload token — set CANOPY_E2E_AUTH_TOKEN or write the token to "
        f"{TOKEN_FILE} (chmod 600). The token must match canopy-web's "
        f"CANOPY_E2E_AUTH_TOKEN.",
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


_ATTR_RE = re.compile(
    r"""(\b(?:src|href|poster)\s*=\s*)(['"])([^'"]+?)(\2)""",
    re.IGNORECASE,
)
_CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^)'"]+?)\1\s*\)""", re.IGNORECASE)


def _looks_remote(ref: str) -> bool:
    # data:, http:, https:, //cdn, mailto:, #anchor, etc.
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
    # Strip query/fragment for filesystem lookup.
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


def http_json(
    url: str,
    method: str = "GET",
    body: dict | None = None,
    cookiejar: http.cookiejar.CookieJar | None = None,
    timeout: int = 30,
) -> tuple[int, dict, http.cookiejar.CookieJar]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    if cookiejar is None:
        cookiejar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookiejar))
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {"error": e.reason}
        return e.code, payload, cookiejar
    raw = resp.read()
    payload = json.loads(raw.decode("utf-8")) if raw else {}
    return resp.status, payload, cookiejar


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


def http_multipart(
    url: str,
    fields: dict[str, str],
    file_field: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
    cookiejar: http.cookiejar.CookieJar,
    csrf_token: str | None = None,
    timeout: int = 120,
) -> tuple[int, dict]:
    body, ct = _build_multipart(fields, file_field, filename, content_type, file_bytes)
    headers = {"Content-Type": ct}
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
        # Django expects Referer to match the host on CSRF-protected POSTs.
        parsed = urlparse(url)
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookiejar))
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {"error": e.reason}
        return e.code, payload
    raw = resp.read()
    payload = json.loads(raw.decode("utf-8")) if raw else {}
    return resp.status, payload


def _csrf_from_jar(jar: http.cookiejar.CookieJar) -> str | None:
    for c in jar:
        if c.name == "csrftoken":
            return c.value
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="canopy:walkthrough-share",
        description="Upload a walkthrough to canopy-web.",
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
        "--as", dest="email_override", metavar="EMAIL",
        help=f"Override the upload-as email (must end in @{ALLOWED_DOMAIN})",
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

    email = resolve_email(args.email_override)
    token = resolve_token()
    api = args.api_url.rstrip("/")
    title = (args.title or src.stem).strip()
    visibility = "link" if args.public else "private"

    if kind == "html":
        print(f"inlining HTML assets from {src.parent}…", file=sys.stderr)
        payload_bytes = inline_html(src)
        upload_name = "slideshow.html"
    else:
        payload_bytes = src.read_bytes()
        upload_name = "video.mp4"

    size_mb = len(payload_bytes) / (1024 * 1024)
    print(f"uploading {size_mb:.1f} MB to {api} as {email}…", file=sys.stderr)

    jar = http.cookiejar.CookieJar()
    status, body, jar = http_json(
        f"{api}/api/auth/e2e-login/",
        method="POST",
        body={"email": email, "token": token},
        cookiejar=jar,
    )
    if status != 200:
        fail(f"e2e-login failed (HTTP {status}): {_describe_error(body)}")

    # Bootstrap a CSRF cookie before the multipart POST — Django requires it
    # for session-authenticated POSTs.
    csrf_status, _, jar = http_json(f"{api}/api/csrf/", method="GET", cookiejar=jar)
    if csrf_status not in (200, 204):
        fail(f"csrf bootstrap failed (HTTP {csrf_status})")
    csrf = _csrf_from_jar(jar)

    fields = {
        "title": title,
        "kind": kind,
        "description": args.description,
        "visibility": visibility,
    }
    if args.project_slug:
        fields["project_slug"] = args.project_slug

    status, body = http_multipart(
        f"{api}/api/walkthroughs/",
        fields=fields,
        file_field="file",
        filename=upload_name,
        content_type=content_type,
        file_bytes=payload_bytes,
        cookiejar=jar,
        csrf_token=csrf,
    )
    if status != 201:
        fail(f"upload failed (HTTP {status}): {_describe_error(body)}")

    # canopy-web migrated DRF → Django Ninja in May 2026 — responses are now
    # bare typed payloads (no {success, data, timing_ms} envelope). Read
    # fields directly off `body`.
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
