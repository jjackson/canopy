# Manager sync — fleet-canonical process (canopy agent-core)

**Fleet-canonical process.** Your `skills/manager-sync/SKILL.md` stub carries your Identity
(name, `<slug>`, mailbox, who your advisor is, which gdoc/email tools you use) — apply this doc
bound to that identity. To change THIS process for the whole fleet, PR canopy
(`plugins/canopy/agent-core/manager-sync.md` + `canopy version bump`); agent-specific quirks go in
your stub's local-notes section.

A **manager sync** is a recurring, honest report to your advisor — the human whose scarce time
steers you. You report what you did since the last sync, **grade yourself harshly** on both the
work and how well you built reusable skills, and put a short list of already-decided next steps to
them to confirm or redirect. The sync is a first-class object on your canopy-web workspace
(`/agents/<slug>`), not a loose doc: it stores the doc link + a summary + your self-grades, and the
window state lives there — **not in a repo file.**

## The window (state lives on canopy-web)
- Read your last sync: `canopy agent syncs --slug <slug> --limit 1`. The window is that sync's
  `period_end` → today (`date +%Y-%m-%d`). First ever sync (empty list): from your project start.
- Do NOT keep `last_sync` in a repo file. The posted sync IS the record; a repo file drifts and
  splits state across the fleet.
- **An empty list means "no syncs", so sanity-check it before trusting a project-start window.**
  If your board or mailbox shows a sync you clearly sent, the window is wrong — don't re-report
  months of already-reported work. (A client bug once returned `[]` for every agent; the fix is
  in, but the cross-check is free and the failure is expensive.)

## Correcting a posted sync
- `canopy agent sync …` is **idempotent per (period_start, period_end, source)** — re-posting the
  SAME window overwrites it. So fixing a grade, summary, or doc URL is just posting again; it does
  NOT pile up duplicates.
- That also means a sync filed under the **wrong period** can't be corrected by re-posting — it
  lands as a second record. Remove it with `canopy agent sync-delete --slug <slug> --id <id>`
  (get the id from `canopy agent syncs`). Use it only for a wrong-period or stray row.

## Gather everything in the window
- **Completed work — from your board, the first-class source:** `canopy agent tasks --slug <slug>`.
  Every task `done` in the window is a completed item; its `score` + `review` were captured when it
  was marked done (see *Scoring at completion*). Tasks still open are your in-flight list.
- **Skills/code:** `git log --since=<period_end> --oneline` in your repo (skills built/changed, PRs).
- **Deliverables + comms:** your sent mail in the window; the gdocs/forms/decks produced; any backlog.
- Cross-check: work that shipped WITHOUT a board task is a tracking gap — name it in the sync and
  add the task now, so the next sync is complete by construction.

## Scoring at completion (not at sync time)
Grade each task **when you mark it done**, not weeks later at sync time:
`canopy agent set --slug <slug> --task-id <N> --status done --score <grade> --review "<one line>"`.
`score` is a short grade (`A-`, `B+`, `4/5`); `review` is the blunt one-liner. The sync then READS
those completion scores instead of re-grading from memory. If a task closed unscored, grade it in
the sync AND backfill it with the same `set` call so the board and the sync agree.

## Write the sync — the structure
Grades are **merged into the items**, never a separate table. Sections, in order:

1. **Headline** — two or three lines: overall self-grades (work + skill-building) and the one thing
   that matters most this window. Blunt.
2. **Completed this window** — one entry per completed board task: **title (linked to the task /
   its deliverable) — score.** one-line review. Pull the score/review from the task's completion
   fields. Note any work that shipped untracked as an honest process gap.
3. **Open / in-flight** — a quick bulleted list of in-progress + queued tasks, each linked, with the
   next action. Don't grade these.
4. **Skills built / improved** — a bulleted list with **copyable source links** (the SKILL.md on
   GitHub), because people read the sync to reuse them. Add the honest skill-building ding here:
   foresight, or scar tissue from avoidable errors? what's still unbuilt?
5. **Questions / prototypes to share** — see *Asks discipline*. Concrete decisions to confirm, and
   any prototype/example worth a look.

## Harshness rule
Be your own toughest critic. **If your advisor could grade it lower than you did, you graded it
wrong.** Name failures specifically — the wrong recipient, the broken link, the doc no one could
open, the thing a human had to redo — not vaguely. Self-congratulation wastes their time.

## Asks discipline (your advisor's scarce time)
Your advisor is the **advisor, not the requester**. Two rules:
- **Propose, don't poll.** If you can ask a question, you can propose an answer — so do. Every ask
  is a decision you've ALREADY made, stated with its alternative, for them to confirm or redirect.
  An open-ended question ("where should I focus?", "any feedback?") wastes their time: if you don't
  already know what you'd do with the answer, you have nothing to act on — so don't ask it.
- **Task-specific questions go to the requester, not the advisor.** A question about a particular
  deliverable — who owns a stat, which framing someone wants, whether a doc opened — belongs in that
  person's thread; route it there. What's left for the advisor is portfolio-level: where your hours
  go, how to sequence the big bets, and whether your self-grades are honestly calibrated.

## Pre-send review
The sync report (email/message to your advisor) is an outbound deliverable — run your
`agent-turn-review` gate on it before it goes: fidelity to this structure, grounded commitments
(every "next I'll…" names an executable mechanism), and presentation (lead with what you DID,
enumerate, link every skill as source, verify the recipient). Don't skip it because it's "just a
status update."

## Publish + record (this is the state)
1. Publish the sync as a shareable doc via your gdoc tool; verify it renders clean and is shared
   before the link goes out (no leaked markdown, no unshared doc — the same delivery hygiene you're
   grading yourself on).
2. Record it on canopy-web — this is what makes it first-class and what the NEXT window reads:
   `canopy agent sync --slug <slug> --doc-url <url> --title "<title>" --summary "<one-liner>"
   --grades '{"work":"<grade>","skills":"<grade>"}' --period-start <ISO> --period-end <ISO>`.
3. Refresh your skill catalog so the workspace mirrors reality: `canopy agent skills --slug <slug>
   --from-repo <skills-dir> --url-template <github-blob-url>` (your stub wraps this).
4. Draft the report to your advisor (gated send — a human approves it) leading with the headline and
   linking the doc + your **syncs feed** (`…/w/<workspace>/agents/<slug>/syncs`). Link the SECTION,
   not the bare `/agents/<slug>` — that redirects to the workspace default (`inbox`), not your
   syncs. Same for a board reference: link `…/agents/<slug>/tasks`.

## Related
`agent-turn-review` (per-deliverable pre-send gate; manager-sync is the periodic portfolio view),
`task-tracker` (the board this reads), `turn` (a sync is a kind of turn output).
