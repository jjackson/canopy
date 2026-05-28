---
name: ddd-why-brief
description: |
  Draft a why-brief (why_brief.yaml) from an evidence inventory produced by
  ddd-evidence-audit. Builds an ordered narrative spine where each claim links
  to evidence; unsupported/assumed claims become Gaps tagged RESEARCH /
  CAPABILITY / DECISION. Loops until python -m scripts.ddd.validate passes.
  Use when asked to "draft the why-brief", "write why-brief", or after
  ddd-evidence-audit completes.
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# DDD Why-Brief

Transform raw evidence into a structured narrative spine: an ordered sequence
of claims, each grounded in evidence, with explicit gaps for anything unproven.
The why-brief (`why_brief.yaml`) is the narration spine for the later video
walkthrough and the source of truth for the "why" of the feature.

## Inputs

- **`evidence_json`** — path to `evidence.json` produced by `ddd-evidence-audit`.
- **`run_dir`** — directory to write `why_brief.yaml` (same dir as evidence.json by default).
- **`feature_name`** — name of the feature (read from evidence.json if not supplied).

## Procedure

### Step 1 — Read evidence.json

```bash
cat <run_dir>/evidence.json
```

Load and parse the evidence inventory.  Note the feature name, total item count, and how many items are `assumed` vs `documented`/`implemented`.

### Step 2 — Draft `problem`

Write one clear, specific sentence that states the problem this feature solves.  This sentence becomes the top-level `problem:` field in `why_brief.yaml` (not inside any spine item).  The problem statement must:
- Name who has the problem (user role / actor)
- Name what is painful or missing
- Be falsifiable — a reader can imagine evidence that confirms or refutes it

Do NOT use hedge language like "might", "could potentially", or "may help".

### Step 3 — Draft the spine

Build an ordered list of `SpineItem` objects.  Each spine item is one narrative beat: a claim that advances from "the problem exists" → "the problem is solvable in this way" → "our approach is the right one".

**For each claim:**
1. Write `claim` — a single assertive sentence.
2. Write `rationale` — 1-3 sentences explaining why this claim follows from the previous one or from first principles.  Must not be empty.
3. Attach `evidence` refs from evidence.json.  Use the item's `id` as the `ref`.  Tag each with `kind` matching the evidence item's kind.
4. Set `status`:
   - `"grounded"` — ONLY if ≥1 evidence item with `kind` != `assumed` is attached.
   - `"gap"` — if all evidence is assumed, or no evidence is attached.

**Provenance rule:** every spine item `id` must be `S1`, `S2`, … (sequential, no gaps).  These IDs become the `provenance` fields in the later unified spec.

**Ordering:** the spine should read as a logical argument.  A reader who accepts each claim should naturally accept the next.

### Step 4 — Draft gaps

For every spine item with `status: "gap"` (or with only assumed evidence), create a `Gap`:

- `id` — `G1`, `G2`, … (sequential).
- `type` — one of:
  - `RESEARCH` — we don't know if the claim is true; requires field research, user interviews, or data analysis.
  - `CAPABILITY` — we believe the claim is true but lack the technical or organisational capability to act on it; feeds the build loop.
  - `DECISION` — a trade-off that requires human judgment; surfaces to the user at the concept gate.
- `claim_ref` — the `SpineItem.id` this gap belongs to.
- `detail` — what specifically is unknown or unresolved.
- `proposed_action` — concrete next step to close the gap.

**Gap routing:** DECISION gaps surface to the user at the concept gate; CAPABILITY gaps feed the build loop; RESEARCH gaps spawn autonomous investigation.

### Step 5 — Write why_brief.yaml

Write the draft to `<run_dir>/why_brief.yaml`.  The schema is:

```yaml
schema_version: 1
feature: <feature_name>
problem: <problem statement>
spine:
  - id: S1
    claim: <claim>
    rationale: <rationale>
    status: grounded | gap
    evidence:
      - kind: documented | implemented | assumed
        ref: <EV-id or path or URL>
  # ... more spine items
gaps:
  - id: G1
    type: RESEARCH | CAPABILITY | DECISION
    claim_ref: S1
    detail: <what is unknown>
    proposed_action: <next step>
  # ... more gaps
```

### Step 6 — Validate and loop

Run the structural validator:

```bash
python -m scripts.ddd.validate why_brief <run_dir>/why_brief.yaml
```

If it exits non-zero, read each problem listed and fix `why_brief.yaml`.  Re-run until the validator exits 0.  After 3 fix attempts, if the validator still exits non-zero, stop and surface the remaining errors to the user rather than looping further.

Common fixes:
- `grounded but no non-assumed evidence` → change `status` to `gap` or add real evidence.
- `Gap claim_ref not found` → update `claim_ref` to match an existing `SpineItem.id`.
- `duplicate spine id` → renumber spine items.
- `rationale` empty → fill in the rationale sentence.

### Step 7 — Report

After the validator passes, print:

```
Why-Brief — <feature_name>
══════════════════════════════════════

  Problem:  <problem statement>
  Spine items: N (grounded: X, gap: Y)
  Gaps:        N (RESEARCH: A, CAPABILITY: B, DECISION: C)

  Output: <run_dir>/why_brief.yaml
  Validator: PASS

Next step: run /ddd-why-qa for structural QA, then /ddd-why-eval for LLM scoring.
```

If there are DECISION gaps, list them explicitly:

```
  ⚠ DECISION gaps (require human judgment before proceeding):
    G<n>: <detail> → proposed_action: <action>
```
