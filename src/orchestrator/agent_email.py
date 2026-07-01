"""Shared guarded email engine for the agent fleet — backs `canopy email`.

The generalization of echo's `bin/echo_email.py` + `bin/echo_mark_read.py` (adopted by
ACE as `bin/ace-email` / `bin/ace-mark-read`). Implements §3 of
docs/architecture/shared-gog-gdrive.md: the send wrapper, mark-read, and preflight are
ENGINE (fix-once-propagate, lives here); each agent supplies only its MOUNTS — mailbox +
gog client name in its repo's `config/agent.json` (`email`, `gog_client`).

Three subcommands:

- `send` — HTML multipart send via gog. Why HTML: Gmail display-wraps plain text at a
  fixed ~72 columns, which reads as ugly hard line breaks; an HTML body reflows to the
  reader's width. So we build flowing <p> paragraphs + <ul> bullets + linkified URLs,
  with a plain-text alternative, and send both. Body-file contract: single-line
  paragraphs separated by blank lines; bullet lines ("- ", "* ", "1. ") one per line —
  normalize() also collapses accidental hard-wrapped paragraphs.
  Emits a JSON result with `message_id` + `thread_id`; the SEND-SIDE CONTRACT is that
  every caller records `thread_id` into the agent's state layer (ACE: run comms-log;
  echo: contact-memory) so inbound triage can route the reply.
- `mark-read` — remove the UNREAD label via the Gmail API with the agent's own gog
  OAuth (gog has no mark-read command, and API reads don't clear the flag).
- `preflight` — gog auth liveness for the agent's client, with the exact `gog login …`
  remediation (and the API-not-enabled self-heal echo's preflight learned the hard way).

Identity is per-agent and never shared: one mailbox + one gog client per agent
(`credentials-<client>.json` in the gogcli config dir) — reusing another agent's client
is the session/thread identity bleed the fleet was built to avoid.
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import click

from orchestrator.agent_web import AgentWebError, resolve_identity
from orchestrator.repo_paths import resolve_repo_path

GOG_CONFIG_DIR = os.path.expanduser("~/Library/Application Support/gogcli")
# Every Google surface a turn commonly touches — one login covers them all, so an
# agent doesn't re-consent per service. gmail is the only one THIS engine needs.
LOGIN_SERVICES = "gmail,drive,docs,sheets,forms"

LIST_RE = re.compile(r"^\s*([-*+]|\d+\.)\s+")
URL_RE = re.compile(r"(https?://[^\s<>()]+)")


class AgentEmailError(Exception):
    """Raised for identity/config problems or a failed send."""


@dataclass
class EmailIdentity:
    slug: str        # agent slug, e.g. "hal"
    account: str     # mailbox, e.g. hal@dimagi-ai.com
    client: str      # gog client name (credentials-<client>.json), usually == slug


def resolve_email_identity(repo_dir: Path) -> EmailIdentity:
    """Resolve the agent's email identity from its repo (plugin.json + config/agent.json).

    Mailbox comes from agent.json `email`; the gog client from agent.json `gog_client`,
    defaulting to the slug (the fleet convention: client name == agent slug).
    """
    try:
        ident = resolve_identity(Path(repo_dir))
    except AgentWebError as e:
        raise AgentEmailError(str(e)) from e
    account = (ident.get("email") or "").strip()
    if not account:
        raise AgentEmailError(
            f"no mailbox for agent {ident['slug']!r} — add \"email\" to "
            f"{Path(repo_dir) / 'config' / 'agent.json'}"
        )
    client = (ident.get("gog_client") or "").strip() or ident["slug"]
    return EmailIdentity(slug=ident["slug"], account=account, client=client)


def find_agent_repo(slug: str) -> Path:
    """Locate an agent repo by slug across the machine's emdash root conventions."""
    path = resolve_repo_path(slug)
    if path is None:
        raise AgentEmailError(
            f"no local repo found for agent {slug!r} — pass --repo <dir> explicitly"
        )
    return path


# --------------------------------------------------------------------------------------
# Body shaping (ported verbatim from echo's proven wrapper)
# --------------------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Collapse hard-wrapped prose to one line per paragraph; keep bullets/blank lines."""
    out: list[str] = []
    para: list[str] = []

    def flush():
        if para:
            out.append(" ".join(s.strip() for s in para))
            para.clear()

    for ln in text.split("\n"):
        s = ln.rstrip()
        if not s.strip():
            flush()
            out.append("")
        elif LIST_RE.match(s):
            flush()
            out.append(s.strip())
        else:
            para.append(s)
    flush()
    collapsed: list[str] = []
    for line in out:
        if line == "" and collapsed and collapsed[-1] == "":
            continue
        collapsed.append(line)
    return "\n".join(collapsed).strip() + "\n"


def _linkify(escaped: str) -> str:
    return URL_RE.sub(lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', escaped)


def to_html(plain: str) -> str:
    blocks = re.split(r"\n\s*\n", plain.strip())
    parts = []
    for b in blocks:
        lines = [l for l in b.split("\n") if l.strip()]
        if lines and all(LIST_RE.match(l) for l in lines):
            lis = "".join(
                f"<li>{_linkify(html.escape(LIST_RE.sub('', l).strip(), quote=False))}</li>"
                for l in lines
            )
            parts.append(f"<ul>{lis}</ul>")
        else:
            text = " ".join(l.strip() for l in lines)
            parts.append(f"<p>{_linkify(html.escape(text, quote=False))}</p>")
    return ('<html><body style="font-family:Arial,Helvetica,sans-serif;'
            'font-size:14px;line-height:1.5;color:#222">' + "".join(parts) + "</body></html>")


# --------------------------------------------------------------------------------------
# send
# --------------------------------------------------------------------------------------

def build_send_command(
    identity: EmailIdentity,
    *,
    to: str,
    subject: str,
    plain_path: str,
    html_body: str,
    cc: str | None = None,
    reply_to_message_id: str | None = None,
) -> list[str]:
    cmd = ["gog", "gmail", "send", "--account", identity.account, "--client", identity.client,
           "--to", to, "--subject", subject,
           "--body-file", plain_path, "--body-html", html_body, "--json"]
    if cc:
        cmd += ["--cc", cc]
    if reply_to_message_id:
        cmd += ["--reply-to-message-id", reply_to_message_id]
    return cmd


def parse_send_result(stdout: str) -> dict:
    """Normalize gog's --json send output to {message_id, thread_id, raw}.

    Liberal on key names (id/messageId vs message_id, threadId vs thread_id) so a gog
    version bump doesn't silently drop the thread_id the routing contract depends on.
    """
    try:
        raw = json.loads(stdout)
    except (ValueError, TypeError):
        return {"message_id": "", "thread_id": "", "raw": (stdout or "").strip()}
    obj = raw if isinstance(raw, dict) else {}
    message_id = obj.get("message_id") or obj.get("messageId") or obj.get("id") or ""
    thread_id = obj.get("thread_id") or obj.get("threadId") or ""
    return {"message_id": str(message_id), "thread_id": str(thread_id), "raw": raw}


def send(
    identity: EmailIdentity,
    *,
    to: str,
    subject: str,
    body_text: str,
    cc: str | None = None,
    reply_to_message_id: str | None = None,
    dry_run: bool = False,
    runner=subprocess.run,
) -> dict:
    """Send an HTML multipart email as the agent. Returns the normalized JSON result.

    dry_run renders the plain + HTML bodies without invoking gog.
    """
    plain = normalize(body_text)
    html_body = to_html(plain)
    if dry_run:
        return {"dry_run": True, "account": identity.account, "client": identity.client,
                "to": to, "subject": subject, "plain": plain, "html": html_body}
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
        tf.write(plain)
        plain_path = tf.name
    try:
        cmd = build_send_command(
            identity, to=to, subject=subject, plain_path=plain_path,
            html_body=html_body, cc=cc, reply_to_message_id=reply_to_message_id,
        )
        r = runner(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise AgentEmailError(
                f"gog gmail send failed (exit {r.returncode}) as {identity.account}: "
                f"{(r.stderr or r.stdout or '').strip()[:400]}"
            )
        return parse_send_result(r.stdout)
    finally:
        os.unlink(plain_path)


# --------------------------------------------------------------------------------------
# mark-read
# --------------------------------------------------------------------------------------

def _refresh_token(identity: EmailIdentity, *, runner=subprocess.run) -> str:
    """The agent's gog refresh token: env override, else the macOS keychain entry gog wrote."""
    env_key = identity.slug.upper().replace("-", "_") + "_GOOGLE_REFRESH_TOKEN"
    if os.environ.get(env_key):
        return os.environ[env_key].strip()
    r = runner(
        ["security", "find-generic-password", "-s", "gogcli", "-a",
         f"token:{identity.client}:{identity.account}", "-w"],
        capture_output=True, text=True,
    )
    raw = (r.stdout or "").strip()
    if r.returncode != 0 or not raw:
        raise AgentEmailError(
            f"no gog refresh token in the keychain for {identity.account} (client "
            f"{identity.client}) — run: gog login {identity.account} "
            f"--client {identity.client} --services {LOGIN_SERVICES}"
        )
    return json.loads(raw)["refresh_token"]


def gmail_access_token(
    identity: EmailIdentity,
    *,
    gog_dir: str | None = None,
    runner=subprocess.run,
    opener=urllib.request.urlopen,
) -> str:
    """Mint a Gmail API access token from the agent's own gog OAuth client + refresh token."""
    creds_path = os.path.join(gog_dir or GOG_CONFIG_DIR, f"credentials-{identity.client}.json")
    try:
        creds = json.load(open(creds_path))
    except OSError as e:
        raise AgentEmailError(
            f"gog client credentials missing: {creds_path} — copy the agent's OWN OAuth "
            f"client JSON there (1Password AI-Agents), never another agent's"
        ) from e
    body = urllib.parse.urlencode({
        "client_id": creds["client_id"], "client_secret": creds["client_secret"],
        "refresh_token": _refresh_token(identity, runner=runner),
        "grant_type": "refresh_token"}).encode()
    with opener("https://oauth2.googleapis.com/token", body) as r:
        return json.load(r)["access_token"]


def mark_read(
    identity: EmailIdentity,
    thread_ids: list[str],
    *,
    token: str | None = None,
    gog_dir: str | None = None,
    runner=subprocess.run,
    opener=urllib.request.urlopen,
) -> list[dict]:
    """Remove the UNREAD label from each thread as the agent. Per-thread results, keeps going."""
    tok = token or gmail_access_token(identity, gog_dir=gog_dir, runner=runner, opener=opener)
    results = []
    for th in thread_ids:
        req = urllib.request.Request(
            f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{th}/modify",
            data=json.dumps({"removeLabelIds": ["UNREAD"]}).encode(),
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            method="POST")
        try:
            with opener(req):
                results.append({"thread_id": th, "ok": True, "error": ""})
        except Exception as e:  # noqa: BLE001 — report per-thread, keep going
            results.append({"thread_id": th, "ok": False, "error": str(e)[:200]})
    return results


# --------------------------------------------------------------------------------------
# preflight
# --------------------------------------------------------------------------------------

def _oauth_remedy(identity: EmailIdentity, stderr: str) -> list[str] | None:
    """Targeted fix for *API-not-enabled* failures (NOT a bad token — re-login won't help).

    The self-heal for the "accessNotConfigured" dead-end that stalled an echo turn on a
    fresh machine: gog is authed fine, but a Google API isn't enabled in the agent's
    OAuth project. Returns fix lines including the enable URL Google embeds, else None.
    """
    s = stderr or ""
    if not re.search(r"accessNotConfigured|SERVICE_DISABLED|has not been used in project|"
                     r"API has not been used", s, re.I):
        return None
    api = "A required Google API"
    am = re.search(r"([A-Z][\w ]*? API) has not been used", s)
    if am:
        api = am.group(1)
    url_m = re.search(r"https://console\.(?:developers|cloud)\.google\.com/\S+", s)
    lines = [
        f"FIX: {api} is not enabled for {identity.slug}'s OAuth project.",
        "     gog IS authed — this is NOT a token problem, so re-login won't fix it.",
        (f"     Enable it: {url_m.group(0).rstrip('.),')}" if url_m
         else "     Enable the API in the Google Cloud console for the agent's OAuth project."),
        "     Then wait ~1 min for it to propagate and re-run this preflight.",
    ]
    return lines


def preflight(
    identity: EmailIdentity,
    *,
    gog_dir: str | None = None,
    runner=subprocess.run,
) -> tuple[bool, list[str]]:
    """Is the agent's gog Gmail auth alive? (ok, report-lines) — read-only, never logs in."""
    gog_home = gog_dir or GOG_CONFIG_DIR
    login_cmd = (f"gog login {identity.account} --client {identity.client} "
                 f"--services {LOGIN_SERVICES}")
    creds = os.path.join(gog_home, f"credentials-{identity.client}.json")
    if not os.path.exists(creds):
        return False, [
            f"FIX: gog `{identity.client}` client credentials missing: {creds}",
            f"     Copy {identity.slug}'s OWN OAuth client JSON there (1Password AI-Agents).",
            f"     Do NOT reuse another agent's client — identity bleed is the fleet's one hard rule.",
            f"     Then: {login_cmd}",
        ]
    cfg_path = os.path.join(gog_home, "config.json")
    mapped = False
    if os.path.exists(cfg_path):
        try:
            mapped = (json.load(open(cfg_path)).get("account_clients", {})
                      .get(identity.account) == identity.client)
        except (ValueError, OSError):
            mapped = False
    if not mapped:
        return False, [
            f"FIX: {cfg_path} does not map {identity.account} -> {identity.client}.",
            f"     Add it under account_clients (or re-run: {login_cmd})",
        ]
    # Live token check: a read-only search confirms the refresh token is good.
    try:
        r = runner(
            ["gog", "gmail", "search", "--account", identity.account,
             "--client", identity.client, "in:inbox", "--max", "1"],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        return False, ["FIX: gog CLI not installed (brew install gog / see GOG docs)."]
    except subprocess.TimeoutExpired:
        return False, ["FIX: gog gmail search timed out — check network / re-login."]
    if r.returncode != 0:
        remedy = _oauth_remedy(identity, r.stderr)
        if remedy:
            return False, remedy
        first_err = (r.stderr or "").strip().splitlines()[:1]
        return False, [
            f"FIX: gog `{identity.client}` creds present but not logged in / token bad.",
            f"     Run: {login_cmd}",
            f"     ({first_err[0] if first_err else 'no token'})",
        ]
    return True, [f"OK: gog Gmail ready (account {identity.account}, client {identity.client})."]


# --------------------------------------------------------------------------------------
# CLI — `canopy email …`
# --------------------------------------------------------------------------------------

def _identity_from_opts(repo: str | None, agent: str | None,
                        account: str | None, client: str | None) -> EmailIdentity:
    if account:  # fully explicit identity — no repo needed
        return EmailIdentity(slug=agent or account.split("@")[0],
                             account=account, client=client or agent or account.split("@")[0])
    repo_dir = Path(repo) if repo else (find_agent_repo(agent) if agent else Path.cwd())
    ident = resolve_email_identity(repo_dir)
    if client:
        ident.client = client
    return ident


_identity_options = [
    click.option("--repo", type=click.Path(exists=True, file_okay=False),
                 help="Agent repo root (default: cwd). Identity from its config/agent.json."),
    click.option("--agent", help="Agent slug — locate its local repo instead of --repo."),
    click.option("--account", help="Explicit mailbox override (skips repo resolution)."),
    click.option("--client", help="Explicit gog client override."),
]


def _with_identity_options(fn):
    for opt in reversed(_identity_options):
        fn = opt(fn)
    return fn


@click.group("email")
def email_group():
    """Guarded agent email — shared engine, per-agent identity (shared-gog-gdrive.md §3)."""


@email_group.command("send")
@_with_identity_options
@click.option("--to", required=True, help="Comma-separated recipients.")
@click.option("--cc")
@click.option("--subject", required=True)
@click.option("--body-file", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Plain-text body: single-line paragraphs, blank-line separated; '- ' bullets.")
@click.option("--reply-to-message-id", help="Thread the send as a reply to this message id.")
@click.option("--dry-run", is_flag=True, help="Render plain + HTML bodies without sending.")
def email_send(repo, agent, account, client, to, cc, subject, body_file,
               reply_to_message_id, dry_run):
    """Send an HTML multipart email as the agent (the fleet's ONLY send path).

    Emits JSON with message_id + thread_id — record thread_id into the agent's state
    layer (comms-log / contact-memory) so inbound triage can route the reply.
    """
    try:
        ident = _identity_from_opts(repo, agent, account, client)
        result = send(
            ident, to=to, subject=subject, body_text=Path(body_file).read_text(),
            cc=cc, reply_to_message_id=reply_to_message_id, dry_run=dry_run,
        )
    except AgentEmailError as e:
        raise click.ClickException(str(e))
    click.echo(json.dumps(result, indent=2))


@email_group.command("mark-read")
@_with_identity_options
@click.argument("thread_ids", nargs=-1, required=True)
def email_mark_read(repo, agent, account, client, thread_ids):
    """Remove the UNREAD label from THREAD_IDS via the Gmail API (gog has no mark-read)."""
    try:
        ident = _identity_from_opts(repo, agent, account, client)
        results = mark_read(ident, list(thread_ids))
    except AgentEmailError as e:
        raise click.ClickException(str(e))
    failed = 0
    for res in results:
        if res["ok"]:
            click.echo(f"{res['thread_id']} -> read")
        else:
            failed += 1
            click.echo(f"{res['thread_id']} -> ERROR {res['error']}")
    if failed:
        sys.exit(1)


@email_group.command("preflight")
@_with_identity_options
def email_preflight(repo, agent, account, client):
    """Check the agent's gog Gmail auth is alive; print the exact remediation if not."""
    try:
        ident = _identity_from_opts(repo, agent, account, client)
    except AgentEmailError as e:
        raise click.ClickException(str(e))
    ok, lines = preflight(ident)
    for line in lines:
        click.echo(line)
    if not ok:
        sys.exit(1)
