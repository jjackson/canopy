---
description: Run autonomous PM sprints in a self-pacing loop — sprint, send email, wait for "keep going" or 24h timeout, repeat.
allowed-tools: [Read, Glob, Grep, Bash, Agent, Write, Edit]
---

# /canopy:pm-autonomous-loop

Wraps `/canopy:pm-autonomous` so it can run sprint-after-sprint without you re-typing the command each time.

## Process

1. Run one full sprint by invoking `/canopy:pm-autonomous` end-to-end (read `pm-autonomous.md` for the full procedure).

2. After the sprint sends its email and exits, ENTER WAIT STATE:
   - Sleep until either:
     - The user sends a follow-up message that does NOT match (case-insensitive, anchored at start, whole-word) `^(stop|pause|halt)\b`, OR
     - 24 hours have passed since the email was sent.
   - Use the `loop` skill (`/loop`) in dynamic mode for the wait — pass `<<autonomous-loop-dynamic>>` per its docs so the runtime resolves it.

3. On wake (either case):
   - If the wake was due to the 24h timeout, send a single non-nagging reminder ping via `email.sender_skill`: `Subject: <prefix> Autonomous PM sprint paused — say 'keep going' to resume`. Then re-enter wait state for another 24h cycle.
   - If the wake was a user message that DOES match `^(stop|pause|halt)\b`, exit cleanly — print "Stopping autonomous loop. Run /canopy:pm-autonomous-loop again to resume." and end.
   - Otherwise, treat ANY user message as resume. Start the next sprint.

4. Repeat from step 1 until exit.

## Notes

- The 24h timeout is hardcoded for v1. If you want a different cadence, run `/canopy:pm-autonomous` directly (single sprint, no loop) and re-invoke this command on your own schedule.
- The loop only ever holds ONE autonomous PR in flight at a time (enforced by the autonomous cycle's Phase 0).
- If the user-supplied resume message contains substantive guidance ("focus on adoption-blockers next", "skip the dogfood pass"), the next sprint should treat it as a high-priority hint in Phase A scouting.
