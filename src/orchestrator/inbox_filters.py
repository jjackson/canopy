"""Fleet inbox filters — the junk guard, defined ONCE for the whole fleet and
applied to any/all agent mailboxes via gog Gmail filters. Conservative by design:
only obviously automated / marketing mail is skipped-inbox + marked-read, so a real
message from a person never gets silently archived.

Edit ``FILTERS`` and re-run ``canopy email apply-filters`` to update the fleet — this
is the single source of truth for the whole fleet's inbox hygiene.

Two operations:
- ``apply_filters``   — create the Gmail filters (affect FUTURE mail). Idempotent.
- ``sweep_existing``  — retroactively archive+mark-read mail already in the inbox that
  the filters would have caught (clears the backlog so it doesn't spawn turns).
"""
from __future__ import annotations

import json
import subprocess

# Each rule: a Gmail match `query` + actions. Keep this list conservative and legible.
FILTERS: list[dict] = [
    {
        "name": "automated-noreply",
        "query": 'from:(noreply OR no-reply OR donotreply OR "do-not-reply" OR mailer-daemon OR postmaster)',
        "archive": True, "mark_read": True,
    },
    {"name": "promotions", "query": "category:promotions", "archive": True, "mark_read": True},
    {"name": "social", "query": "category:social", "archive": True, "mark_read": True},
]


class FilterError(Exception):
    pass


def _existing_queries(mailbox: str, client: str, *, runner=subprocess.run) -> set[str]:
    try:
        r = runner(["gog", "gmail", "settings", "filters", "list",
                    "--account", mailbox, "--client", client, "--json"],
                   capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    if r.returncode != 0:
        return set()
    try:
        items = json.loads(r.stdout or "{}").get("filters") or []
    except ValueError:
        return set()
    return {(f.get("criteria") or {}).get("query") for f in items if (f.get("criteria") or {}).get("query")}


def apply_filters(mailbox: str, client: str, *, runner=subprocess.run, dry_run: bool = False) -> dict:
    """Create the FILTERS on one mailbox, idempotently (skip ones already present).
    Gmail filters affect FUTURE mail only — pair with sweep_existing for the backlog."""
    existing = _existing_queries(mailbox, client, runner=runner)
    applied, skipped = [], []
    for flt in FILTERS:
        if flt["query"] in existing:
            skipped.append(flt["name"])
            continue
        cmd = ["gog", "gmail", "settings", "filters", "create",
               "--account", mailbox, "--client", client, "--query", flt["query"]]
        if flt.get("archive"):
            cmd.append("--archive")
        if flt.get("mark_read"):
            cmd.append("--mark-read")
        if flt.get("add_label"):
            cmd += ["--add-label", flt["add_label"]]
        if dry_run:
            cmd.append("--dry-run")
        r = runner(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise FilterError(f"filter '{flt['name']}' on {mailbox}: {r.stderr.strip() or 'gog failed'}")
        applied.append(flt["name"])
    return {"applied": applied, "skipped": skipped}


def sweep_existing(mailbox: str, client: str, *, runner=subprocess.run, dry_run: bool = False) -> dict:
    """Retroactively archive + mark-read mail ALREADY in the inbox that a filter would
    catch — so an existing junk backlog doesn't spawn turns when polling starts."""
    swept = {}
    for flt in FILTERS:
        q = f'in:inbox ({flt["query"]})'
        r = runner(["gog", "gmail", "search", "--account", mailbox, "--client", client,
                    q, "--max", "50", "--json"], capture_output=True, text=True, timeout=45)
        if r.returncode != 0:
            raise FilterError(f"sweep search '{flt['name']}' on {mailbox}: {r.stderr.strip()}")
        try:
            threads = json.loads(r.stdout or "{}").get("threads") or []
        except ValueError:
            threads = []
        ids = [t["id"] for t in threads if t.get("id")]
        swept[flt["name"]] = len(ids)
        if ids and not dry_run:
            # archive (remove from inbox) + mark read, by thread
            for action in ("archive", "mark-read"):
                a = runner(["gog", "gmail", "thread", "modify", "--account", mailbox, "--client", client,
                            *(["--remove-label", "INBOX"] if action == "archive" else ["--remove-label", "UNREAD"]),
                            *ids], capture_output=True, text=True, timeout=45)
                # best-effort; don't abort the whole sweep on one action
    return swept
