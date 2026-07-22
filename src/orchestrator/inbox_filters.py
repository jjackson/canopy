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
    # Out-of-office / auto-reply bounces. These wake an agent for zero-content mail:
    # Ada's 2026-07-20 conduct cycle caught Beth's "Offline through July 26th…" auto-reply
    # spawning a full eva turn (which correctly did nothing — pure wasted tokens). Gmail
    # can't match the RFC Auto-Submitted/Precedence headers, so match the high-precision
    # auto-reply subject markers instead. Marking read on arrival means the runner's
    # `is:unread` poll never sees it — the turn is never spawned. A later REAL reply in the
    # same thread arrives unread and triggers normally, so nothing is permanently silenced.
    {
        "name": "auto-reply-ooo",
        "query": ('subject:("out of office" OR "automatic reply" OR "auto-reply" OR autoreply '
                  'OR "away from my email" OR "away from the office" OR "offline through" '
                  'OR "offline until")'),
        "archive": True, "mark_read": True,
    },
    # Google Calendar "share my calendar" invitations. Ada's 2026-07-22 review caught one
    # (Beth sharing her calendar) spawn a full eva turn that spelunked the Calendar API before
    # concluding "no action." Same shape as the OOO rule: it's auto-generated
    # (Auto-Submitted: auto-generated) but Gmail can't match that header — and worse, the
    # From: is SPOOFED to the human sharer (Sender: is calendar-notification@google.com), so
    # a from: filter would either miss it or archive the person's real mail. Match the exact
    # high-precision subject the share-invite always carries. Real event invites/RSVPs use
    # different subjects and are NOT matched. (Docs/Drive share pings stay unfiltered — those
    # carry real work routing; a calendar SHARE invite does not.)
    {
        "name": "calendar-share-invites",
        "query": 'subject:("invitation to join shared calendar" OR "invitation to view shared calendar")',
        "archive": True, "mark_read": True,
    },
    # Ada's first fleet audit (2026-07-14) found ~90 junk threads across agent inboxes,
    # dominated by these three senders (hal alone: 45 GitHub notifications, 10 Google
    # Cloud upsells, 4 Expensify). Agents work GitHub via the gh CLI, never via email.
    # Google Docs/Drive share notifications are deliberately NOT filtered — they carry
    # real work routing (how an agent learns a doc was shared with it).
    {
        "name": "github-notifications",
        "query": "from:notifications@github.com",
        "archive": True, "mark_read": True,
    },
    {
        "name": "google-cloud-marketing",
        "query": "from:googlecloud@google.com",
        "archive": True, "mark_read": True,
    },
    {
        "name": "expensify",
        "query": "from:(concierge@expensify.com OR notifications@expensify.com)",
        "archive": True, "mark_read": True,
    },
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
    catch — so an existing junk backlog doesn't spawn turns when polling starts.

    Counts reflect threads whose modify actually SUCCEEDED, and each rule pages
    past gog's per-search result cap until its matches are drained. (Ada's
    2026-07-14 fleet sweep reported 184 'swept' messages that never moved: the
    modify used a nonexistent --remove-label flag, its result was discarded, and
    search matches were reported as swept. Never count what you didn't verify.)
    """
    swept = {}
    for flt in FILTERS:
        q = f'in:inbox ({flt["query"]})'
        done = 0
        for _page in range(20):  # safety bound: 20 pages × 50 = 1000 threads/rule/run
            r = runner(["gog", "gmail", "search", "--account", mailbox, "--client", client,
                        q, "--max", "50", "--json"], capture_output=True, text=True, timeout=45)
            if r.returncode != 0:
                raise FilterError(f"sweep search '{flt['name']}' on {mailbox}: {r.stderr.strip()}")
            try:
                threads = json.loads(r.stdout or "{}").get("threads") or []
            except ValueError:
                threads = []
            ids = [t["id"] for t in threads if t.get("id")]
            if not ids:
                break
            if dry_run:
                done += len(ids)
                break  # can't drain pages without modifying — report first page only
            failures = []
            for tid in ids:
                # one call archives AND marks read the whole thread
                a = runner(["gog", "gmail", "thread", "modify", tid, "--remove=INBOX,UNREAD",
                            "--account", mailbox, "--client", client, "--no-input"],
                           capture_output=True, text=True, timeout=45)
                if a.returncode == 0:
                    done += 1
                else:
                    failures.append(tid)
            if failures:
                # matched threads we couldn't modify would repeat forever — stop this rule
                # loudly rather than spin; partial success is still reported in the count.
                raise FilterError(
                    f"sweep '{flt['name']}' on {mailbox}: modify failed for "
                    f"{len(failures)}/{len(ids)} threads (e.g. {failures[0]})")
        swept[flt["name"]] = done
    return swept
