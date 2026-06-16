#!/usr/bin/env python3
"""Upload the current Claude Code session transcript to canopy-web.

Used by /canopy:share-session. Stdlib only — bare ``python3`` runs it.

Flow:
  1. Resolve the transcript .jsonl. Default: the newest file under
     ``~/.claude/projects/<cwd-slash-encoded>/`` (same dir Claude Code writes
     the live session to). Override with a positional path.
  2. Resolve config (api URL, PAT at ~/.claude/canopy/workbench-token).
  3. POST it multipart to /api/sessions/upload with Authorization: Bearer.
     The server parses, best-effort-scrubs secrets, and (link-by-default)
     mints a share token.
  4. Print the /share/<token> URL and the redaction count.

Auth: canopy-web's PersonalToken (PAT). Mint with /canopy:canopy-web-pat-mint.

Exits non-zero on any failure with a one-line ``error: …`` on stderr.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_API = "https://canopy-web-ujpz2cuyxq-uc.a.run.app"
TOKEN_FILE = Path.home() / ".claude" / "canopy" / "workbench-token"


def fail(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


# Harness-authored "user" lines that aren't things the human typed.
_NOISE_PREFIXES = (
    "<system-reminder",
    "<command-name",
    "<command-message",
    "<command-args",
    "<local-command-stdout",
    "<local-command-stderr",
    "<local-command-caveat",
    "<task-notification",
    "<system>",
    "Caveat:",
    "[Request interrupted",
)


def _is_noise(text: str) -> bool:
    t = text.lstrip()
    return any(t.startswith(p) for p in _NOISE_PREFIXES)


def reduce_transcript(path: Path) -> tuple[bytes, int]:
    """Reduce a raw Claude .jsonl to a clean conversation, client-side.

    Keeps only what the human typed and the FINAL assistant text of each turn.
    Drops tool_use / tool_result / sidechain / harness-noise entirely — they
    are never uploaded. Re-emits a minimal Claude-format .jsonl (init + user/
    assistant text lines) that the server parses back into exactly these turns.

    The full noisy transcript (and any sensitive tool output it carries) never
    leaves the machine.
    """
    session_id = ""
    turns: list[tuple[str, str]] = []  # (role, text) in order
    pending_assistant: str | None = None

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue

        kind = e.get("type")
        if kind == "system" and e.get("subtype") == "init":
            session_id = e.get("session_id", "") or session_id
            continue
        if e.get("isSidechain"):
            continue
        msg = e.get("message") if isinstance(e.get("message"), dict) else {}

        if kind == "assistant":
            blocks = msg.get("content", [])
            if isinstance(blocks, list):
                texts = [
                    b.get("text", "")
                    for b in blocks
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                joined = "".join(texts).strip()
                if joined:
                    pending_assistant = joined  # latest assistant text wins
            continue

        if kind == "user":
            content = msg.get("content")
            if not isinstance(content, str):
                continue  # list content == tool_result; ignore
            text = content.strip()
            if not text or _is_noise(text):
                continue
            # flush the previous turn's final assistant reply, then this prompt
            if pending_assistant:
                turns.append(("assistant", pending_assistant))
                pending_assistant = None
            turns.append(("user", text))

    if pending_assistant:
        turns.append(("assistant", pending_assistant))

    out = [json.dumps({"type": "system", "subtype": "init", "session_id": session_id})]
    for i, (role, text) in enumerate(turns):
        text = text.replace("\x00", "")
        if role == "user":
            out.append(json.dumps({"type": "user", "message": {"content": text}}))
        else:
            out.append(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {"id": f"a{i}", "content": [{"type": "text", "text": text}]},
                    }
                )
            )
    return ("\n".join(out) + "\n").encode("utf-8"), len(turns)


def _describe_error(body: dict) -> str:
    if not isinstance(body, dict):
        return str(body)
    detail = body.get("detail")
    title = body.get("title")
    if detail and title:
        return f"{title}: {detail}"
    return detail or title or body.get("error") or str(body)


def resolve_pat() -> str:
    token = os.environ.get("CANOPY_WEB_PAT", "").strip()
    if token:
        return token
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        if token:
            return token
    fail(
        f"no canopy-web PAT — run /canopy:canopy-web-pat-mint to mint one, "
        f"or set CANOPY_WEB_PAT. Expected token at {TOKEN_FILE}.",
    )
    raise SystemExit  # unreachable


def _project_dir_for(cwd: Path) -> Path:
    """Claude Code's transcript dir for a working directory.

    Claude encodes the absolute cwd by replacing each '/' with '-', e.g.
    /Users/x/proj → -Users-x-proj, under ~/.claude/projects/.
    """
    encoded = str(cwd).replace("/", "-")
    return Path.home() / ".claude" / "projects" / encoded


def discover_transcript(cwd: Path) -> Path:
    proj = _project_dir_for(cwd)
    if not proj.is_dir():
        fail(
            f"no Claude session log dir for {cwd} (looked in {proj}). "
            f"Pass the transcript path explicitly, or run this from the "
            f"project where the session ran.",
        )
    candidates = sorted(
        proj.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        fail(f"no .jsonl transcripts found in {proj}")
    return candidates[0]


def _build_multipart(
    fields: dict[str, str], filename: str, file_bytes: bytes
) -> tuple[bytes, str]:
    boundary = "----canopysess" + base64.urlsafe_b64encode(os.urandom(9)).decode("ascii")
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
    parts.append(b"Content-Type: application/x-ndjson")
    parts.append(b"")
    body = crlf.join(parts) + crlf + file_bytes + crlf + f"--{boundary}--".encode() + crlf
    return body, f"multipart/form-data; boundary={boundary}"


def upload(
    url: str, pat: str, fields: dict[str, str], filename: str, file_bytes: bytes
) -> tuple[int, dict]:
    body, ct = _build_multipart(fields, filename, file_bytes)
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": ct, "Authorization": f"Bearer {pat}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {"error": e.reason}
        return e.code, payload
    raw = resp.read()
    return resp.status, (json.loads(raw.decode("utf-8")) if raw else {})


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="canopy:share-session",
        description="Upload the current Claude session transcript to canopy-web.",
    )
    p.add_argument(
        "path",
        nargs="?",
        help="Transcript .jsonl (default: newest for the current dir's session).",
    )
    p.add_argument("--title", help="Session title (default: the transcript stem).")
    p.add_argument("--project", dest="project_slug", help="Project slug for the feed.")
    p.add_argument(
        "--private",
        action="store_true",
        help="Upload private (dimagi-only) instead of link-by-default.",
    )
    p.add_argument(
        "--full",
        action="store_true",
        help="Upload the raw transcript (all tool calls). Default reduces to "
        "the conversation — your prompts + Claude's final reply per turn — "
        "client-side, so tool output never leaves your machine.",
    )
    p.add_argument(
        "--api-url",
        default=os.environ.get("CANOPY_WEB_API_URL", DEFAULT_API),
        help="canopy-web base URL (default: %(default)s)",
    )
    args = p.parse_args(argv)

    cwd = Path.cwd()
    if args.path:
        src = Path(args.path).expanduser().resolve()
        if not src.is_file():
            fail(f"transcript not found: {src}")
    else:
        src = discover_transcript(cwd)
        print(f"using transcript: {src}", file=sys.stderr)

    pat = resolve_pat()
    api = args.api_url.rstrip("/")
    title = (args.title or src.stem).strip()
    project = args.project_slug or cwd.name
    visibility = "private" if args.private else "link"

    if args.full:
        file_bytes = src.read_bytes()
    else:
        file_bytes, n_turns = reduce_transcript(src)
        print(
            f"reduced to {n_turns} conversation turn(s) "
            f"(prompts + final replies; tool calls dropped client-side)",
            file=sys.stderr,
        )
    size_kb = len(file_bytes) / 1024
    print(f"uploading {size_kb:.0f} KB to {api}…", file=sys.stderr)

    fields = {"title": title, "visibility": visibility}
    if project:
        fields["project_slug"] = project

    status, body = upload(
        f"{api}/api/sessions/upload", pat, fields, src.name, file_bytes
    )
    if status != 201:
        fail(f"upload failed (HTTP {status}): {_describe_error(body)}")

    slug = body.get("slug")
    if not slug:
        fail(f"unexpected response: {body}")

    redactions = body.get("redaction_count", 0)
    msg_count = body.get("message_count", 0)
    token = body.get("share_token")

    if body.get("duplicate"):
        print("(already shared — returning the existing link)", file=sys.stderr)

    if visibility == "link" and token:
        print(f"Share: {api}/share/{token}")
    else:
        print(f"View (dimagi login required): {api}/sessions  (slug: {slug})")
    print(
        f"{msg_count} messages · {redactions} secret"
        f"{'' if redactions == 1 else 's'} redacted (best-effort)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
