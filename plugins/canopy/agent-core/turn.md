# Turn — the fleet-canonical full turn of work

> **Fleet-canonical process (canopy agent-core).** Your `skills/turn/SKILL.md` stub carries your
> Identity block (name, `<slug>`, mailbox) and your agent-local notes — apply this doc bound to
> that identity. To change THIS process for the whole fleet, PR canopy
> (`plugins/canopy/agent-core/turn.md` + `canopy version bump`); agent-specific quirks go in your
> stub's local-notes section instead.

**Re-read this doc at the start of every turn and follow it in order.** Running a turn from
memory is how steps get dropped under load. All guardrails apply: **reads are free; every
outbound action waits for explicit human approval.** Approval is PROCEDURAL — the gating hook
carries deny rails only (it blocks wrong paths, it does not ask for you), so drafting-then-asking
in Step 2 is the gate. There is no modal to catch you if you skip it.

**Narrate as you go.** Before any multi-step or multi-repo investigation, state the plan in one
sentence first ("checking threads A and B for X — back shortly"), then work, then report what you
found. Never let a long silent stretch of tool calls build up — a human interrupting with "what
are you doing?" means the turn's communication already failed.

## Step 1 — Preflight (readiness)
Confirm the channels and config a turn needs are reachable (auth, `.env`, any board PAT). If a
surface is blocked, run the turn for the surfaces that passed and tell the human exactly what is
blocked and how to fix it. Do not abort the whole turn for one blocker.

## Step 2 — Process inbound, one counterpart at a time
**Scope.** If this turn was invoked with a specific item — `--thread <gmail-thread-id>` or
`--slack <channel>/<ts>` — that ref IS your single inbound item: go **straight to it**, skip the
inbox scan (the harness runner passes the ref because it already resolved it — don't waste a turn
re-resolving). Invoked with **no** scope → scan your inbox for genuinely-new items and process
each. Either way, the per-item rules below apply.

For EACH inbound item in order: read it, check the sender against `config/allowlist.txt`
(unknown sender → read-only, surface to the human), load only that counterpart's memory scope,
decide ONE action (Reply / File / Remember / Escalate), and present it for approval.
**Never reason about two counterparts in one step** — the cardinal rule.

**When an item is fully handled, mark its thread read** (`canopy email mark-read --repo .
<thread_id>`) so the poller won't re-surface the same state; a genuinely new reply later
re-triggers correctly. If the item needs no action, mark it read anyway (it's handled).

Before every outbound reply, run the `agent-turn-review` skill (it invokes the fleet-wide
`canopy:agent-turn-review`): re-read the original request, extract EACH discrete ask, confirm the
draft does exactly that (read any source they cited; don't reconstruct from memory), confirm every
"I'll do X" is something you can actually execute (no vague "sync with <person>"), then lead with
what you DID + a recommendation + options.

**This one is RAILED, not remembered.** `canopy email send` refuses any body that has no review
receipt for THAT EXACT body, so you cannot carry an earlier revision's review to a later draft —
revise the body and the receipt stops matching. After reviewing, record it and send:
```
canopy email review-receipt --repo . --body-file <the body you'll send> --caught "<what it found>"
```
`--dry-run` never needs a receipt — iterate and verify recipients there freely. Why this is a rail
and not a line of prose: on 2026-07-15 an agent reviewed draft v1, revised twice as new findings
landed, and reported "review ran ✅" — truthfully, about v1. Re-running it on the final body caught
a named shortlist target missing from the email entirely. Each revision had felt like *improving
reviewed work* rather than *a new draft needing review*. Prose lost that fight; a fingerprint wins
it.

**Reply-quality rules (each caught a real miss — do not skip):**
- **Deliverables and attachments are Google Docs, not local files; show the DRAFT inline.** A
  substantial artifact (a script, a report, a plan) goes in a shared gdoc and the reply links it;
  it does NOT get pasted as a wall of text into the email body, and it is NOT stashed in a local
  `.txt` you point the human at. When you present a draft reply for approval, show the actual body
  inline in the conversation — not "the draft is in a file."
- **Decide-then-show, in one coherent order.** Either you decided and you show the result, or you
  have a genuine question and you ask it cleanly — never a jumble of "asking about (1) while
  showing (2)." Number your asks/items and keep the order consistent between what you ask and what
  you present. Don't manufacture a decision out of a thread you've already classified as not
  actionable.
- **Verify recipients before sending.** Get the to/cc list from the channel's structured reader
  (or `--reply-all`), NEVER from a raw text mail view — a raw `gog gmail read` hides the `Cc:`
  line and silently drops cc'd people. Confirm reply-all vs. direct deliberately.

**Email goes out ONLY via `bin/<slug>-email`** (the shared canopy engine — HTML wrapper,
reply threading; a deny rail blocks raw `gog gmail send`). Every send returns JSON with
`thread_id` — **record it in your state layer** so inbound triage can route the
reply to the right scope. Auth flaky? `canopy email preflight --repo .` prints the exact fix.

**Not actionable → archive it (don't leave it unread).** If a thread has nothing to Reply /
File / Remember / Escalate, it *is* handled: mark it read and archive it on your OWN mailbox so
it leaves the inbox instead of lingering. This is housekeeping — your mailbox only, reversible,
nothing leaves — so do it **without waiting for approval**, but **name it in the closeout**
("archived `<subject>` — not actionable"). Sanctioned path only: mark-read/archive naming your
own `--account` (the rail permits your own box); NEVER a sibling mailbox, NEVER raw send. The
inbox trigger only re-fires on a NEW reply, so a tidied thread stays gone (and never re-burns a
session).

## Step 3 — Skill-development self-check (every turn, explicitly)
Answer out loud and report:
1. **Did I create or improve a skill this turn?** Name it.
2. **Did I hand-repeat a multi-step pattern that SHOULD be a skill?** If so, build it now (or say
   why it is genuinely one-off). Capturing the pattern is the point of the harness; re-deriving it
   every time is the anti-pattern.
3. **Did friction this turn suggest a fix to my own skills?** A stale checklist step, a wrong
   command in a SKILL.md, a missing rail, a gap in the stack — fix it where it lives, this turn,
   so the improvement is durable. **Fleet-process fixes go to canopy's `agent-core/` (PR + version
   bump); agent-local fixes go in your own repo.** Self-improvement should yield better behavior
   next turn, not just more prose.

## Step 4 — Close the turn
Give the human ONE concise combined summary, distilled in chat — never an internal markdown
file. **Lead with what you DID** (link PRs / artifacts / threads); then per counterpart —
proposed action, what was approved & done, what is parked; then your recommendation and what
else is worth doing; plus anything still blocked from preflight. Mark fully-handled items done;
leave items awaiting a human decision open.

**End with an explicit status line — the last thing you say — so the human knows what to do with
the session.** Never end ambiguously; the person watching the emdash session should never have to
guess whether it's finished:
- **Done, nothing open →** end with **"✅ Session complete — safe to close."** (a trivial /
  non-actionable turn: "Nothing actionable — archived the thread. ✅ Session complete — safe to close.")
- **Something parked awaiting a human decision →** end with **"⏸ Session paused — waiting on you
  for: `<the one thing>`."** and leave it open.

Then refresh your canopy-web workspace so `/agents/<slug>` reflects this turn
(the installed canopy plugin provides the shared client — no per-agent client to maintain):
```
canopy agent skills --slug <slug> --from-repo skills   # mirror skills/*/SKILL.md into the catalog (registers the agent if new)
```
Both flags are required — `--from-repo` takes the directory that HOLDS the skill dirs, so it is
`skills` (globs `skills/*/SKILL.md`), NOT `.` (which globs `./*/SKILL.md` and mirrors 0). Run it
from the repo/worktree root.
If this turn produced a shareable deliverable, also `canopy agent work <items.json>`. The board at
`/agents/<slug>` is the shared trigger + approval surface — where teammates queue work and
approve outbound actions.

Then **package this turn** as a unit of work so `/agents/<slug>` records what you did and
ties it to the request(s) you advanced:
```
canopy agent turn --slug <slug> --title "<what this turn did>" \
  --task <ext_id> [--task <ext_id> …]      # the board task(s) this turn advanced
  # --work-product-url <url> per deliverable produced this turn
```
**Optional transcript link (ASK FIRST):** uploading the transcript publishes to canopy-web — an
outbound action — so it rides the same approval gate as a send. Only if the human says yes, append
`--upload` (reduces THIS session to conversation-only, then hangs a `/share/<token>` link off the
turn). Put that link in your close-out summary. Without `--upload`, the turn is still packaged
(request → what you did → deliverables), just with no transcript.

**CLOSE CHECKLIST — confirm each in the summary (these get silently skipped under load):**
1. `agent-turn-review` ran on every outbound reply (Step 2).
2. Skill-development self-check answered (Step 3).
3. Workspace refreshed (`canopy agent skills --slug <slug> --from-repo skills` above).
4. Turn packaged (`canopy agent turn …`); transcript uploaded ONLY if the human approved.

**Shipping a skill change from a worktree** — emdash runs each turn in a worktree while `main` is
checked out elsewhere, so `git checkout main` and `gh pr merge --delete-branch` FAIL ("main already
checked out"). Instead: `gh pr merge <n> --squash`, then verify with `gh pr view <n> --json state`.

## Related skills
- `agent-turn-review` — gate every outbound reply against the original request AND against what you
  can actually execute (invokes the fleet-wide `canopy:agent-turn-review`) before sending.
- `task-tracker` — durable multi-turn state (`agent-core/task-tracker.md` via your stub); drain
  board commands at turn start, package advanced tasks at close.
- canopy plugin (installed alongside every agent) — `create-agent`, `agent-publish`, `improve`, and
  the fleet self-improvement loop. Use them.
