---
name: fleet-align
description: >
  Cross-agent improvement spread — the fleet-level sibling of agent-review. Compares the
  factory-stamped agent fleet (echo, eva, hal, …) against the current canopy factory template
  and each other, and surfaces what to DISTRIBUTE (backport a better/newer version into laggards)
  or PROMOTE (lift a converged pattern into canopy). For every finding it searches the laggards'
  RECENT SESSIONS for evidence the gap actually cost something, and weighs that evidence in a
  judgment pass — a finding with real evidence outranks a speculative one. Then, behind a
  consolidated gate, it ships the change as a PR (dry-run previews; apply opens PRs). Use when
  asked to "align the agents", "spread improvements across agents", "fleet-align", or to run the
  fleet self-improvement loop. Read-only until the gate.
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash "$HOME/emdash-projects/canopy/plugins/canopy/scripts/canopy-update-check.sh" 2>/dev/null || bash "$HOME/.claude/plugins/marketplaces/canopy/plugins/canopy/scripts/canopy-update-check.sh" 2>/dev/null || true)
case "$_CANOPY_UPD" in UPGRADE_AVAILABLE*) echo "$_CANOPY_UPD" ;; esac
```

If output shows `UPGRADE_AVAILABLE <old> <new>`, mention the upgrade once and continue.

# Fleet-align — spread improvements across the agent fleet

`agent-review` measures ONE agent's friction and ships fixes into that agent's repo. `fleet-align`
is the other half: it looks ACROSS agents. Because every agent is factory-stamped from a shared
template, the same artifacts (`skills/turn`, `skills/self-review`, `config/gating.json`) exist in
each — so divergence is precise and computable, not vibes. Two things move:

- **DISTRIBUTE →** a better/newer version of a shared artifact exists (in the template, or a peer);
  backport it into the laggards. Subsumes "agent is stale vs. a newer template."
- **PROMOTE ↑** an artifact evolved beyond the template in ≥2 agents (they converged) → lift it
  back into canopy's factory template so everyone inherits it.
- **RECONCILE ?** divergence with no clear winner / a legacy lineage (e.g. echo, the ancestor) —
  surfaced for a human to harvest, never auto-patched.

**Evidence is the point.** A structural gap only matters if it costs something. For each finding
the tool searches the laggards' recent turns for the moment the change would have helped, and the
judgment pass ranks evidence-backed findings above speculative ones. Zero evidence is a real
result — it says "structurally real, but hasn't bitten yet; low priority."

## Step 1 — Analyze (read-only)

```
canopy fleet-align [--hours N] [--no-llm] [--repo <dir> ...] [--json-output]
```

This discovers agents (marker: `skills/turn/SKILL.md`, so legacy agents like echo are included),
diffs each shared artifact against the factory template + peers, attaches recent-session evidence,
runs the claude -p judgment pass (skip with `--no-llm`), and prints findings **ranked by evidence
first**. Each carries: kind, artifact, reference, laggards, the specific markers, a judge
rationale, a recommended action, and any evidence excerpts.

## Step 2 — Triage

Present the findings as a table (kind · artifact · reference · → laggards · #evidence · action).
Decide implement / defer / skip per finding. Bias:
- **Evidence-backed DISTRIBUTE first** — a stale artifact that already cost a laggard a real miss.
- **PROMOTE** when ≥2 agents converged — that's the strongest signal the template is behind
  (the §1b story: "ACE re-did echo's fixes by hand" → it belonged in canopy).
- **RECONCILE / legacy** — never auto-apply; note what's worth harvesting from the ancestor.

## Step 3 — Execute, behind ONE consolidated gate (dry-run vs apply)

Read-only until here. Then present a single gate: **"open these N PRs?"**

- **dry-run (default preview):** for each accepted finding, show the exact change and PR plan
  without writing anything. For a **DISTRIBUTE-from-template** finding the change is mechanical —
  re-stamp the laggard's artifact from the CURRENT template (`fleet_align.render_patch` returns the
  template text; substitute the agent's identity: `{{AGENT_NAME}}`→name from `config/agent.json`,
  `{{AGENT_SLUG}}`→repo dir name). Show the diff.
- **apply:** for each accepted finding, in the **laggard's own repo** (an emdash worktree; `main`
  is checked out elsewhere): branch → write the file → commit → `gh pr create`. For a **PROMOTE**,
  the PR goes into **canopy** instead (edit the factory template string in
  `src/orchestrator/agent_factory.py`) — and because that touches `plugins/canopy/` indirectly via
  the template, **run `canopy version bump`** and follow the plugin-update flow. Merge per the
  "no human review, merge it yourself" convention. **Never `gh pr merge --delete-branch`** in a
  worktree (main is checked out elsewhere → it fails); use `gh pr merge <n> --squash`.

One PR per finding (or a tight batch). This changes *code* only — it never sends on anyone's
behalf; the runtime reads-free/writes-gated guardrail still holds.

## Step 4 — Measure (close the loop)

Re-run `canopy fleet-align --no-llm` and confirm the targeted divergence is gone (the laggard no
longer shows as stale, the deprecated `approve` rule cleared). Report before→after. A change that
doesn't collapse the finding isn't done — this is what makes it a loop, not a report.

## Notes

- **Gating is delicate.** `config/gating.json` carries agent-specific channel config; don't blind
  re-stamp it. Apply only the specific delta the finding names (e.g. drop the deprecated `approve`
  block, add the missing deny rail *iff the agent has that channel* — heed the applicability note).
- Legacy agents (no `config/agent.json`, e.g. echo) are never treated as stale laggards — they're
  the ancestor. Harvest their good ideas via PROMOTE, don't "fix" them toward the template.
- Backed by `src/orchestrator/fleet_align.py`; sibling to `agent-review`. Design:
  `docs/superpowers/specs/2026-07-03-fleet-align-design.md`.
