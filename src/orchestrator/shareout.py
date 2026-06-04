"""Team shareout briefings — gather a date range of work (Claude Code sessions
+ the author's GitHub PRs) per project, and post the synthesized briefings to
the canopy-web /shareouts feed.

The deterministic parts live here (date math, corpus gathering, payload
shaping, posting). The *synthesis* — turning the corpus into teammate-facing
"what / why / how to leverage" prose — is done by the `canopy:shareout` skill
agent, which reads the gathered corpus and authors the briefings.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

DEFAULT_API = "https://canopy-web-ujpz2cuyxq-uc.a.run.app"
TOKEN_FILE = Path.home() / ".claude" / "canopy" / "workbench-token"

# Corpus bounds — keep the gathered JSON small enough to hand to a synthesis
# agent without blowing its context, while preserving the signal (intent +
# what shipped). Prompts carry the "why"; PR titles/bodies carry the "what".
MAX_SESSIONS_PER_PROJECT = 40
MAX_PROMPTS_PER_SESSION = 30
PROMPT_TRUNCATE = 600
MAX_PRS_PER_PROJECT = 50


# ---------------------------------------------------------------------------
# Date range
# ---------------------------------------------------------------------------


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s.strip())


def resolve_range(
    from_date: str | None = None,
    to_date: str | None = None,
    days: int | None = None,
    today: dt.date | None = None,
) -> tuple[dt.date, dt.date]:
    """Resolve a (start, end) inclusive date window.

    Precedence: explicit dates win, then `days`, then the default (yesterday).
      - no args                -> yesterday, single day
      - --days N               -> the N full days ending yesterday
      - --from only            -> from .. yesterday (or single day if from==yesterday)
      - --to only              -> single day (that date)
      - --from and --to        -> explicit window

    `today` is injectable for testing.
    """
    today = today or dt.date.today()
    yesterday = today - dt.timedelta(days=1)

    if from_date or to_date:
        start = _parse_date(from_date) if from_date else None
        end = _parse_date(to_date) if to_date else None
        if start is not None and end is None:
            end = yesterday if start <= yesterday else start
        if end is not None and start is None:
            start = end
        if start > end:
            raise ValueError(f"--from ({start}) is after --to ({end})")
        return start, end

    if days:
        if days < 1:
            raise ValueError("--days must be >= 1")
        end = yesterday
        start = end - dt.timedelta(days=days - 1)
        return start, end

    return yesterday, yesterday


def _ts_date(ts: str | None) -> dt.date | None:
    """Date portion (UTC) of an ISO timestamp string, or None."""
    if not ts or len(ts) < 10:
        return None
    try:
        return dt.date.fromisoformat(ts[:10])
    except ValueError:
        return None


def session_in_range(session: dict, start: dt.date, end: dt.date) -> bool:
    """True if the session's [first_ts, last_ts] window (by UTC calendar date)
    intersects [start, end]. Sessions missing timestamps are excluded."""
    first = _ts_date(session.get("first_ts"))
    last = _ts_date(session.get("last_ts")) or first
    first = first or last
    if first is None or last is None:
        return False
    return first <= end and last >= start


# ---------------------------------------------------------------------------
# Gather
# ---------------------------------------------------------------------------


def _session_digest(session: dict) -> dict:
    """Read a session's transcript and summarize it for synthesis: the human
    prompts (intent → the 'why'), a tool-usage summary, and MCP servers."""
    from orchestrator.transcripts import (
        extract_tool_calls,
        extract_user_messages,
        read_transcript,
    )

    path = Path(session["path"])
    entries = read_transcript(path)

    prompts = [
        p.strip()[:PROMPT_TRUNCATE]
        for p in extract_user_messages(entries)
        if p.strip()
    ][:MAX_PROMPTS_PER_SESSION]

    tool_counts: dict[str, int] = defaultdict(int)
    for call in extract_tool_calls(entries):
        tool_counts[call.get("name", "?")] += 1
    top_tools = sorted(tool_counts.items(), key=lambda kv: kv[1], reverse=True)[:12]

    return {
        "session_id": session.get("session_id"),
        "first_ts": session.get("first_ts"),
        "last_ts": session.get("last_ts"),
        "user_msgs": session.get("user_msgs"),
        "mcp_servers": session.get("mcp_servers", []),
        "prompts": prompts,
        "tool_summary": [{"name": n, "count": c} for n, c in top_tools],
    }


def fetch_prs(repo: str, start: dt.date, end: dt.date, author: str = "@me") -> list[dict]:
    """Fetch the author's PRs in `repo` touched within [start, end] via gh.

    Best-effort: returns [] when gh is unavailable, unauthenticated, or the
    repo isn't on GitHub. A PR is included when it was created, merged, or last
    updated within the window.
    """
    if not repo or "/" not in repo:
        return []
    fields = "number,title,url,state,body,createdAt,mergedAt,updatedAt"
    try:
        proc = subprocess.run(
            [
                "gh", "pr", "list",
                "--repo", repo,
                "--author", author,
                "--state", "all",
                "--search", f"updated:>={start.isoformat()}",
                "--json", fields,
                "--limit", str(MAX_PRS_PER_PROJECT),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    try:
        raw = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []

    out = []
    for pr in raw:
        created = _ts_date(pr.get("createdAt"))
        merged = _ts_date(pr.get("mergedAt"))
        updated = _ts_date(pr.get("updatedAt"))
        in_window = any(
            d is not None and start <= d <= end for d in (created, merged, updated)
        )
        if not in_window:
            continue
        body = (pr.get("body") or "").strip()
        out.append({
            "number": pr.get("number"),
            "title": pr.get("title"),
            "url": pr.get("url"),
            "state": pr.get("state"),
            "merged_at": pr.get("mergedAt"),
            "created_at": pr.get("createdAt"),
            "body": body[:2000],
        })
    return out


def gather(
    *,
    projects_dir: Path,
    repo_map: dict,
    labels: dict,
    start: dt.date,
    end: dt.date,
    author: str = "@me",
    project_filter: str | None = None,
    fetch_prs_fn=fetch_prs,
) -> dict:
    """Build the per-project corpus for [start, end].

    Returns {"period": {start, end}, "projects": {repo: {sessions, prs}}}.
    `fetch_prs_fn` is injectable for testing.
    """
    from orchestrator.scanner import scan_all_transcripts

    sessions = scan_all_transcripts(projects_dir, repo_map, labels)
    in_range = [s for s in sessions if session_in_range(s, start, end)]

    if project_filter:
        suffix = f"/{project_filter}"
        in_range = [s for s in in_range if (s.get("repo") or "").endswith(suffix)]

    groups: dict[str, list[dict]] = defaultdict(list)
    for s in in_range:
        key = s.get("repo") or s.get("project_key") or "unknown"
        groups[key].append(s)

    projects = {}
    for repo, sess in sorted(groups.items()):
        sess.sort(key=lambda s: s.get("last_ts") or "")
        digests = [_session_digest(s) for s in sess[:MAX_SESSIONS_PER_PROJECT]]
        prs = fetch_prs_fn(repo, start, end, author) if "/" in repo else []
        projects[repo] = {
            "session_count": len(sess),
            "sessions": digests,
            "prs": prs,
        }

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "projects": projects,
    }


# ---------------------------------------------------------------------------
# Post
# ---------------------------------------------------------------------------


def build_post_payload(authoring: dict, source: str) -> dict:
    """Expand the agent's authoring doc into a ShareoutBatchIn body.

    Authoring shape (what the skill agent writes):
      {
        "period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD",
        "author": "jjackson",
        "rollup": {"title","summary","content","links"} | null,
        "projects": [{"project_slug","title","summary","content","links"}, ...]
      }

    The rollup becomes a shareout with project_slug=null. `source` is stamped
    on every item so a re-run cleanly replaces the prior post (server-side
    idempotency is keyed on project+period+source).
    """
    ps = authoring["period_start"]
    pe = authoring["period_end"]
    author = authoring.get("author", "")

    def _item(slug, b):
        return {
            "project_slug": slug,
            "period_start": ps,
            "period_end": pe,
            "title": b["title"],
            "summary": b.get("summary", ""),
            "content": b["content"],
            "links": b.get("links", []),
            "author": author,
            "source": source,
        }

    items = []
    rollup = authoring.get("rollup")
    if rollup:
        items.append(_item(None, rollup))
    for proj in authoring.get("projects", []):
        items.append(_item(proj["project_slug"], proj))
    return {"shareouts": items}


def resolve_pat() -> str | None:
    token = os.environ.get("CANOPY_WEB_PAT", "").strip()
    if token:
        return token
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        if token:
            return token
    return None


def post(payload: dict, api_url: str, token: str, timeout: int = 60) -> tuple[int, dict]:
    """POST a ShareoutBatchIn to canopy-web. Returns (status, body)."""
    url = f"{api_url.rstrip('/')}/api/shareouts/"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {"error": e.reason}
        return e.code, body
    raw = resp.read()
    return resp.status, (json.loads(raw.decode("utf-8")) if raw else {})


def feed_url(api_url: str) -> str:
    return f"{api_url.rstrip('/')}/shareouts"
