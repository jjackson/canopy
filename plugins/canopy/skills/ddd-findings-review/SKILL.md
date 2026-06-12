---
name: ddd-findings-review
description: |
  Product-findings review gate (product_findings) — for runs in
  review_mode: human. After /canopy:ddd-run judges an iteration, posts ALL
  PRODUCT findings to the canopy-web review surface as ONE review: findings
  are clustered (scene + dimension), and every cluster carries evidence
  deep-links — the hosted deck at #scene-<N> AND the hosted video at
  #t=<seconds> (the scene's start offset) — so the user reviews from a single
  link with no manual searching. The user picks implement / skip / defer per
  cluster; the apply subcommand turns the resolved response into a
  machine-readable selection the orchestrator acts on. Nothing is
  auto-applied in human mode.
  Use when asked to "review the findings", "findings gate", "post the
  product findings", or after ddd-run judges an iteration whose spec sets
  review_mode: human.
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash "$HOME/emdash-projects/canopy/plugins/canopy/scripts/canopy-update-check.sh" 2>/dev/null || bash "$HOME/.claude/plugins/marketplaces/canopy/plugins/canopy/scripts/canopy-update-check.sh" 2>/dev/null || true)
case "$_CANOPY_UPD" in UPGRADE_AVAILABLE*) echo "$_CANOPY_UPD" ;; esac
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# DDD Product-Findings Review Gate

This gate exists for **`review_mode: human`** — narratives whose spec opts out
of autonomous fix application. In autonomous mode (the default) the
orchestrator auto-applies PRODUCT findings with `fix_kind: mechanical` and
loops. In human mode, the user picks which PRODUCT findings to implement —
and they should be able to do that from **one link**, with each finding's
evidence (the exact deck capture AND the exact video moment) one click away.
No hand-written chat tables, no scrubbing the clip to find the scene.

## Why this gate exists

Judge findings reference scenes ("Scene 3: the table header uses jargon").
Reviewing them used to mean: open the deck, scroll to the scene, open the
video, drag the playhead around until the scene appears. This gate formalizes
the fix: the recorder stamps per-scene `start_seconds` into the run report,
and each posted finding cluster carries `deck_url#scene-<N>` plus
`clip_url#t=<seconds>` deep-links (the canopy-web `/w/` viewer seeks to
`#t=` on load).

## Inputs

- **`run_id`** — a JUDGED run (`phase: judged`) from `scripts.ddd.runstate`.
  The run dir must contain `design_findings.json` (concept judge),
  `verdict-user.yaml` (user-artifact judge), and `run-report.json` (the
  recorder's per-scene timings). The run_state must carry
  `iteration_decks` / `iteration_clips` for the current iteration (stamped by
  `ddd-run` Step 2b).

## Procedure

### Step 1 — Resolve the canopy repo

```bash
# scripts/ddd ships in the canopy repo, not the plugin cache — resolve it:
DDD_REPO="$HOME/emdash-projects/canopy"; [ -d "$DDD_REPO/scripts/ddd" ] || DDD_REPO="$HOME/.claude/plugins/marketplaces/canopy"
if [ ! -d "$DDD_REPO/scripts/ddd" ]; then echo "ERROR: scripts/ddd not found — run /canopy:update to sync the canopy checkout"; exit 1; fi
```

### Step 2 — Check the mode (skip this gate in autonomous mode)

```bash
SPEC_ABS="$(realpath docs/walkthroughs/<narrative-slug>.yaml)"
(cd "$DDD_REPO" && uv run python -m scripts.ddd.findings_review mode "$SPEC_ABS")
# prints: autonomous | human
```

If the mode is `autonomous`, STOP — this gate does not apply. Route findings
per the standard table in `agents/ddd.md` (mechanical PRODUCT findings
auto-apply).

### Step 3 — Post the findings review

Run from the TARGET repo's directory (the run dir resolves from the CWD's git
toplevel), with `uv run` pointed at the canopy repo:

```bash
(cd "$DDD_REPO" && uv run --project "$DDD_REPO" python -m scripts.ddd.findings_review post "<run_id>")
# To run from the target repo's CWD instead (so .canopy/ddd resolves there):
PYTHONPATH="$DDD_REPO" uv run --project "$DDD_REPO" python -m scripts.ddd.findings_review post "<run_id>"
```

The command:

- reads `design_findings.json` + `verdict-user.yaml` + `run-report.json`
  from the run dir, and `iteration_decks` / `iteration_clips` from run_state;
- clusters PRODUCT findings by scene + dimension (an explicit `cluster` key
  on a finding overrides), merging severity/fix_kind worst-of;
- attaches per-cluster evidence links: `deck#scene-<N>` and `clip#t=<sec>`;
- posts ONE `gate: product_findings` review with implement/skip/defer
  decisions per cluster plus one overall decision;
- **stamps `run_state.yaml`** with `findings_review_id` +
  `findings_review_url` — do NOT stamp by hand;
- prints JSON: `{posted, id, clusters, internal_url, share_url, ...}`.

Flags: `--spec <path>` (when the spec isn't at
`docs/walkthroughs/<narrative_slug>.yaml`), `--deck-url` / `--clip-url`
(override the run_state URLs).

If it prints `{"posted": false, "reason": "no PRODUCT findings to review"}`,
there is nothing to gate — continue the loop on the remaining
CONCEPT/RESEARCH/DEFER routes.

### Step 4 — Present the URL + inline summary table

Present the **`internal_url`** (owner view, left rail) as the single review
link, plus a compact summary so the user can react without leaving the chat:

```
Product findings review — <narrative-slug> (iteration <N>)
══════════════════════════════════════════════════════════
Judges: concept <X>/5 · user-artifact <Y>/5 — <M> PRODUCT finding cluster(s)

| # | Cluster | Sev | Fix kind | Scenes | Evidence |
|---|---------|-----|----------|--------|----------|
| 1 | <title> | high | mechanical | 2 | deck#scene-2 · video@0:42 |
| 2 | <title> | med  | options    | 3 | deck#scene-3 · video@1:21 |

▶ Review and decide at: <internal_url>
```

Use the real deep-link URLs from the post output's `findings[].evidence`
(don't retype them). Only hand out `share_url` when the user explicitly wants
to share externally.

### Step 5 — Await and apply the user's response

Poll `review.await_resolution` (or wait for the inline response). Once
resolved, write the `response_json` to a temp file and parse the selection:

```bash
RESPONSE_JSON_FILE="$(mktemp /tmp/findings_response_XXXXXX.json)"
# Write the resolved response_json to $RESPONSE_JSON_FILE, then:
(cd "$DDD_REPO" && uv run python -m scripts.ddd.findings_review apply "$RESPONSE_JSON_FILE")
```

Prints the machine-readable selection:

```json
{"overall": "proceed with selected",
 "selections": [{"cluster_id": "scene-2-visual-polish", "decision": "implement"}],
 "implement": ["scene-2-visual-polish"],
 "skip": ["scene-3-clarity"],
 "defer": ["user-trust"]}
```

### Step 6 — Gate: route on the selection

| Outcome | Effect |
|---------|--------|
| `overall == "proceed with selected"` | Apply ONLY the `implement` clusters (their `suggested_fix`), log `skip` to the digest, append `defer` clusters to learnings/backlog. Then re-fire `/canopy:ddd-run` on the same scope. |
| `overall == "discuss"` | Do NOT apply anything. Surface the clusters inline and have the conversation; re-post after it resolves. |

Unknown/missing decisions are treated as `defer` — never auto-apply on
ambiguity.

### Step 7 — Report

```
DDD Findings Gate — <narrative-slug> (iteration <N>)
══════════════════════════════════════
  Overall:     proceed with selected | discuss
  Implement:   <n> cluster(s) — <ids>
  Skip:        <n> cluster(s)
  Defer:       <n> cluster(s)
  Review URL:  <internal_url>

  <If proceed:> Applying <n> fixes, then re-firing /canopy:ddd-run.
  <If discuss:> Holding — nothing applied.
```

## Important

- This gate fires **only** when the spec sets `review_mode: human`
  (`UnifiedSpec.review_mode`; default `autonomous`). Check with
  `findings_review mode <spec_path>` — never guess.
- In human mode, **nothing is auto-applied** — not even mechanical PRODUCT
  findings. The review IS the application decision.
- CONCEPT / RESEARCH / DEFER findings are NOT part of this gate — they keep
  their standard routing (`agents/ddd.md` § Route findings).
- Per standing policy, this gate posts to the **canopy-web review surface**,
  never `AskUserQuestion`.
- Video deep-links require the recorder's per-scene timings
  (`run-report.json` → `scenes[]`). Old runs without them degrade to
  deck-only evidence — that's expected, not an error.
