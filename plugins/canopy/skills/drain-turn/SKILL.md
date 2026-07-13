---
name: drain-turn
description: >
  Execute one canopy-web harness turn for an agent: resolve the active turn,
  mark it running, drain the agent's pending board commands, then finish the
  turn. Invoked by the emdash automation the canopy runner triggers — this
  skill IS the body of an automated agent turn. Usage: /canopy:drain-turn <agent-slug>
---

# Drain turn

Execute exactly ONE automated harness turn for agent `$1` against canopy-web.
This is the body of an automated turn — the canopy runner (`packages/canopy_runner`
in canopy-web) triggers an emdash automation whose prompt is
`/canopy:drain-turn <agent-slug>`; this skill is what that automation runs.

**Base URL:** read `CANOPY_WEB_URL` from the environment; default to
`https://labs.connect.dimagi.com/canopy`.

**Auth:** send `Authorization: Bearer $(cat ~/.claude/canopy/workbench-token)`
on every request (the PAT minted by `/canopy:canopy-web-pat-mint`).

## Process

1. **Resolve the turn.**
   ```bash
   curl -s "{base}/api/harness/turns/?agent=$1&status=claimed,running" \
     -H "Authorization: Bearer $TOKEN"
   ```
   Exactly one turn is expected (the harness enforces one active turn per
   agent at a time).
   - **Zero turns** → say "no active turn for $1" and STOP. Do not invent
     work, do not poll — the runner will trigger you again when a turn exists.
   - **More than one** → that's a harness invariant violation; report it and
     STOP rather than guessing which to act on.
   - Note the turn's `id` and `prompt` from the response.

2. **Mark it running.**
   ```bash
   curl -s -X POST "{base}/api/harness/turns/{id}/start" \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"session_id": ""}'
   ```

3. **Do the work.**
   - If the turn's `prompt` is non-empty, follow it as your instructions for
     this turn.
   - Otherwise the default work is a **board drain**:
     ```bash
     curl -s "{base}/api/agents/$1/commands?status=pending" \
       -H "Authorization: Bearer $TOKEN"
     ```
     For each pending command, act under your normal guardrails — the same
     rules as a human-triggered turn (writes gated, no external sends
     without approval) — then mark it applied:
     ```bash
     curl -s -X POST "{base}/api/agents/$1/commands/{cmd_id}/apply" \
       -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
       -d '{"result_note": "<one line: what you did>"}'
     ```

4. **Report.** Append a one-line ledger event summarizing the turn:
   ```bash
   curl -s -X POST "{base}/api/harness/turns/{id}/events" \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"events": [{"kind": "status", "payload": {"status": "work_summary", "summary": "<one line>"}}]}'
   ```
   `kind` must be one of: `status`, `assistant`, `tool_start`, `tool_end`,
   `question`, `approval`, `error`, `heartbeat` — anything else 422s at the
   API boundary.

5. **Finish.** ALWAYS finish the turn, even on error:
   ```bash
   curl -s -X POST "{base}/api/harness/turns/{id}/finish" \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"status": "done", "result_note": "<n> commands applied"}'
   ```
   or on failure:
   ```bash
   curl -s -X POST "{base}/api/harness/turns/{id}/finish" \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"status": "failed", "result_note": "<why>"}'
   ```
   **Never leave the turn unfinished** — if you must stop early for any
   reason, finish with `failed` and an honest `result_note` rather than
   exiting silently. The harness has no other way to learn the turn ended.

## When NOT to use this skill

- **Interactive, human-driven work on an agent** — this skill is only the
  automated-turn body; a human working with an agent directly doesn't need
  it.
- **Setting up the runner itself** — see `packages/canopy_runner/README.md`
  in canopy-web for laptop install, pairing, and the launchd job.
