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

Stamp the review URL onto `run_state.yaml` so `ddd-run`'s upload step can pass
it as the video's `narrative` companion link (the "Back to the narrative" link
on the `/w/<id>` viewer). Prefer the token-bearing URL so a non-owner viewer
can open it:

```python
from scripts.ddd.runstate import load, save
state = load("<run_id>")
state.narrative_review_url = "<review_url>?t=<token>"  # or the server's `url` if already tokenized
save(state)
```

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

## Iteration behavior — how to handle the user's redraft

When the user resolves the gate with `redraft` and `apply_narrative_edits` has
written their edits back to the spec, the following rules govern the next loop
turn. They exist so the iteration is fast, faithful, and doesn't burn the user's
attention on things they've already implicitly decided.

### Always show the resulting artifact in the conversation, not just the URL

After `apply_narrative_edits` resolves and you've posted a fresh review URL,
present the **updated narrative inline in chat** alongside the URL — the new
narrative paragraph + a per-scene beat-by-beat table (number, persona, scene
title, status badge `Existing feature`/`New feature`). A URL alone is the wrong
shape: it forces the user to chase, and most of the time they won't react to
something they have to chase to see. The artifact has to be in front of them in
the conversation so they can react in the same turn. Pull the artifact from
the per-scene `scene.narrative` values so the inline summary matches what they
see on the review surface.

### Fix typos/grammar without asking — defer only on taste

When applying edits to per-scene fields (`narrative`, `show`, feature
`description`/`verify`), clean obvious typos, dropped words, and mangled
grammar without asking the user. Their intent is the content they typed, not
the literal characters; carrying a typo through the loop noises the
actionability eval, the rendered demo, the docs page, and every blind judge
that reads it. A typo on a load-bearing word in a feature's `verify` can fail
the build check.

Test before deferring: *would the next DDD step (actionability eval, render,
build) be cleaner if I just fixed this?* If yes, fix.

**Defer only on irreplaceable taste:**
- Direction/framing — does this beat belong? right level of abstraction?
- Named-entity choices — don't rename a persona to a specific real person, don't
  change "Kano" to a different state without explicit approval.
- External release (already a hard gate).

### Act on edits that imply new structure — don't ask first

When a user's redraft introduces a new capability, persona change, or
structural shift, propagate it through the spec **without asking**. Their edit
IS the answer; asking re-buys their attention on something they've already
decided.

- **New capability in scene narrative** → add the matching spine item (status
  `gap`) + a gap entry with concrete `proposed_action` + features on the
  relevant scene with concrete `verify`s. If the scene now has a different
  central claim, change its `provenance` to point at the new spine item.
- **Persona rename / pronoun change** → propagate through every scene's
  narration + the persona's `name`/`role`/`intro`/`org` + any role text that
  references a beat count.
- **A scene's narration covers multiple distinct claims** (different
  provenances would apply to different sub-actions) → split into one scene per
  claim before posting. Don't ask "want me to split this?" — split, then show.
  See `ddd-spec` § "Scene shape" for the split rule.
- **Retitled a scene** → regenerate the `build_order` entry for the old slug
  with the new slug (or spec_qa will reject the spec).

The exception is genuine taste calls where the user hasn't expressed a
preference: "split into 2 scenes or 3" if both are equally honest, or
"which real person should we name." Those still gate on the user.

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
