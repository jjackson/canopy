---
name: ddd-narrative-review
description: |
  Narrative-agreement gate (concept_change). Posts the demo narrative to the
  review surface for the user's explicit APPROVE or REDRAFT decision BEFORE any
  rendering, judging, or gap-routing. Presents one story beat per scene (the
  concept_claim arc + per-scene features[] + actionability score) so the user can
  approve the narrative as the build plan, or send it back for a re-draft.
  On redraft: loops back to /ddd-spec. On approve: narrative is locked in.
  Must run AFTER ddd-narrative-actionability-eval passes (fail verdict blocks it).
  Use when asked to "agree on the narrative", "narrative gate", or after
  ddd-narrative-actionability-eval passes and before ddd-run.
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# DDD Narrative-Agreement Gate

This gate centers the demo **narrative** — the story the demo tells to a
prospective user — and gets the user's **explicit approve/redraft decision on it
BEFORE any rendering, judging, or gap-routing**.  The narrative is the north star
and the user's irreplaceable-taste call.  Nothing should be built, rendered, or
judged until the story arc is approved.

The posted review now carries:
- **Per-scene `features[]`** — the concrete buildable units the author declared,
  so the user can see at a glance what is being committed to.
- **Actionability score** — from the `ddd-narrative-actionability-eval` that ran
  before this gate, so the user knows whether the narrative is machine-verifiable.

## Why this gate exists

The DDD loop authors a unified spec (scenes with `concept_claim` story beats and
declared `features[]`), QA-gates it structurally and for actionability, then jumps
straight to rendering.  It never stops to ask: *"Is this the story we want to
tell?"*  That is the defect this gate fixes.

## Inputs

- **`spec_path`** — absolute path to the unified spec YAML
  (`docs/walkthroughs/<feature>.yaml`).
- **`run_id`** — the DDD run identifier from `scripts.ddd.runstate`.

## Procedure

### Step 1 — Resolve the canopy repo

```bash
# scripts/ddd ships in the canopy repo, not the plugin cache — resolve it:
DDD_REPO="$HOME/emdash-projects/canopy"; [ -d "$DDD_REPO/scripts/ddd" ] || DDD_REPO="$HOME/.claude/plugins/marketplaces/canopy"
if [ ! -d "$DDD_REPO/scripts/ddd" ]; then echo "ERROR: scripts/ddd not found — run /canopy:update to sync the canopy checkout"; exit 1; fi
```

### Step 2 — Post the narrative for review

Pass the spec path as an absolute path resolved before the `cd`:

```bash
SPEC_ABS="$(realpath <spec_path>)"
(cd "$DDD_REPO" && uv run python -m scripts.ddd.narrative post "$SPEC_ABS" "<run_id>")
```

This returns JSON: `{"id": "<review_id>", "url": "<review_url>", "share_token": "<token>"}`.
Capture the `url`.

### Step 3 — Present the URL + inline storyboard

Before waiting for the user's response, present:

1. **The review URL** — the editable web page where the user reads each story
   beat and can approve or redraft.

2. **The inline storyboard** — a brief scene-by-scene arc so the user knows
   what they are agreeing to without leaving the chat.  Include the per-scene
   `features[]` and the actionability score so the user can judge concreteness
   at a glance.  Format it as:

   ```
   Narrative storyboard — <feature>
   ══════════════════════════════════════
   Actionability score: N/5 (<pass | warn | fail>)

   Scene 1 · <scene title>
     Story beat: <concept_claim>
     Features: <F1.id> — <F1.description> [verify: <F1.verify>]
               <F2.id> — ...

   Scene 2 · <scene title>
     Story beat: <concept_claim>
     Features: ...
   ...

   ▶ Review and approve at: <review_url>
   ```

   Make reviewing easy and inviting.  The user should be able to glance at the
   storyboard, feel whether the arc is right, and either click the link or
   approve/redraft inline.

### Step 4 — Await and apply the user's response

The orchestrator polls `review.await_resolution` (async mode) or waits for the
user's inline response.  Once resolved, write the `response_json` to a
temporary file and apply edits:

```bash
RESPONSE_JSON_FILE="$(mktemp /tmp/narrative_response_XXXXXX.json)"
# Write the resolved response_json to $RESPONSE_JSON_FILE, then:
(cd "$DDD_REPO" && uv run python -m scripts.ddd.narrative apply "$SPEC_ABS" "$RESPONSE_JSON_FILE")
```

The `apply` command folds any `narration_edits` back onto the matching scenes'
`concept_claim` in the spec and prints `{"decision": "<decision>", "edited": <N>}`.

### Step 5 — Gate: route on the decision

| Decision  | Effect |
|-----------|--------|
| `approve` | Narrative is **APPROVED** — proceed to `ddd-run` (Render + Judge). |
| `redraft` | The narrative needs a structural re-draft — **loop back to `/ddd-spec`** to re-draft the narrative from the spine. Do NOT proceed to render. |

Legacy v2 values are accepted by the `apply` command and coerced automatically:
`"agree"`/`"edit"` → `"approve"`; `"rethink"` → `"redraft"`.

**Critical:** Do NOT proceed to Render + Judge until the decision is `approve`.
A `redraft` means the story is not yet right and rendering would be waste.

### Step 6 — Report

Print a brief summary:

```
DDD Narrative Gate — <feature>
══════════════════════════════════════
  Decision:          <approve | redraft>
  Scenes edited:     <N>
  Actionability:     <N>/5 (<pass | warn | fail>)
  Review URL:        <review_url>

  <If approve:>
  Narrative approved ✓ — ready for /ddd-run.

  <If redraft:>
  Redraft requested — looping back to /ddd-spec to re-draft the narrative.
```

## Important

- This gate centers the demo **narrative** and gets the user's explicit
  **approve/redraft** decision **BEFORE any rendering, building, or judging**.
- The posted review carries per-scene `features[]` and the actionability score
  from `ddd-narrative-actionability-eval` so the user can judge concreteness.
- `approve` means "the narrative is locked in and we have a build plan."
- On `redraft`, re-run `/ddd-spec` with the same `why_brief` and iterate until
  the narrative is right.
- This is a **blocking `concept_change` pause** — the DDD loop must not advance
  to Render + Judge until this gate resolves with `approve`.
