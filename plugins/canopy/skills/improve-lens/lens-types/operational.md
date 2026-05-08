# Operational Lens Runner

You are running canopy's **operational lens** against a target project. Your job: identify execution-fidelity issues — phases failing silently, MCP atoms retrying excessively, gates not being read, state drift — and draft fixes to the orchestrator / agents / MCP atoms / state-management code.

## Status: leans on canopy:session-review

The operational lens overlaps heavily with canopy's existing session-review infrastructure (`canopy:session-review` already detects friction patterns from session logs). v1 implementation: the operational lens calls into session-review's analysis but augments the input with ACE-specific evidence (run_state.yaml, gate-briefs, comms-log/observations).

When session-review's findings shape and the operational lens's signal taxonomy converge (likely in v2), this runner becomes a thin adapter; for now it implements the augmentation and signal-detection itself.

## Inputs

Same as judge/production lens runners.

## Process

### Step 1 — Augment session evidence with ACE per-run state

In addition to recent Claude Code session transcripts, read:

- `<project_dir>/runs/<run-id>/run_state.yaml` — phase status, gate decisions, errors, retries
- `<project_dir>/runs/<run-id>/**/*_gate-brief*.md` — gate-brief content (what each gate flagged)
- `<project_dir>/comms-log/observations.md` (opp-level) — human-curated evidence log
- `<project_dir>/runs/<run-id>/README.md` — orchestrator-written run summary

Read these via the `read_tool` declared in `run-artifacts.yaml`'s `backend_config`. Some entries (e.g. `comms_log`, `eval_calibration`) may have `optional: true` in the descriptor — skip if absent.

### Step 2 — Run signal detectors

For each signal in the descriptor:

- **phase_failed_silently**: cross-reference run_state's `phases.<phase>.status` against the actual artifact set in Drive. If a phase reports `completed` but its declared outputs are missing (per `lib/artifact-manifest.ts`), flag.
- **mcp_atom_retried**: walk session transcripts for tool-call retry clusters. Threshold: 3+ retries on the same atom. Note which atom + what error pattern.
- **gate_brief_not_read**: a gate-brief contains `[WARN]` or `[BLOCKER]` but no human acknowledgment in comms-log/observations within 24h. The orchestrator's surfacing logic didn't escalate.
- **skill_dispatch_drift**: dispatch arguments differ from skill's declared inputs (per artifact-manifest). Note the divergence.
- **state_yaml_corruption**: run_state.yaml has missing/malformed fields the schema validator should have caught.

### Step 3 — Draft proposals

Operational fixes target orchestrator / agents / MCPs / lib code. Targets per descriptor:
- `agents/ace-orchestrator.md`
- `agents/<phase>.md`
- `mcp/<server>/**/*.ts`
- `lib/<lib>.ts`
- `bin/ace-doctor`

Proposal shape same as judge/production. The verification protocol is observational (declared in descriptor), so the dispatcher will:

1. Apply the proposed edit on a worktree.
2. Run `npm test` (or project-declared test command).
3. Run `bin/ace-doctor` (or project's health check).
4. Diff inspection against declared file patterns.
5. Pass if no test regressions and diff matches declared targets.

Operational lens never auto-merges — always human review per descriptor.

### Step 4 — Return findings + proposals

Same YAML shape as judge/production runners. Verification type is `observational`; dispatcher handles the test+doctor+diff steps.

## Important notes

- **Operational changes have the largest blast radius.** Every future /ace:run is affected. Always human review.
- **Don't propose runtime changes from a single failure.** Threshold matters — wait for 2+ occurrences of the same friction pattern before proposing. Single-run anomalies are not operational signals (likely network blips or one-off issues).
- **Defer to session-review's existing taxonomy where it overlaps.** If a finding fits cleanly into canopy's `friction|gap|pattern|missing_capability` taxonomy, surface it that way; canopy:improve will handle it via the standard path. The operational lens is for project-specific signals (phase contracts, gate briefs, MCP atom retries — whatever the project's lens descriptor declares) that the generic session-review can't see without project-specific evidence.
