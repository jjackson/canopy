---
name: ddd-spec-qa
description: |
  Run pure-python structural QA on a unified spec YAML. No LLM — just rules:
  delegates to validate() for persona-defined, provenance-to-spine-id, and
  required-field checks; adds falsifiability check on every Scene.concept_claim
  (fails on empty, whitespace, banned marketing phrases, or fewer than 5 words).
  Returns a Verdict (pass | fail). Gates the concept judge (ddd-concept-judge).
  Use when asked to "qa the spec", "validate spec", or after ddd-spec completes.
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# DDD Unified Spec QA

Structural quality gate for `docs/walkthroughs/<feature>.yaml` before the
concept judge runs.  Pure python — deterministic, fast, no LLM calls.

Implements two layers of checks:

**Layer 1 — delegated to `scripts.ddd.validate` (provenance + persona + schema):**
1. Every `Scene.persona` must be a key in the `personas` dict.
2. When a `why_brief` is declared and resolvable, every `Scene.provenance` must
   match a `SpineItem.id` in that why_brief.
3. All Pydantic-required fields (`name`, `narrative`, `base_url`, `personas`,
   `scenes`) must be present and well-typed.

**Layer 2 — QA-specific (falsifiability of concept_claims):**
4. Every `Scene.concept_claim` must be **non-empty** (whitespace-only fails).
5. Every `Scene.concept_claim` must be **falsifiable** — fails if it:
   - Contains a banned marketing phrase: "world-class", "seamless", "powerful",
     "robust", "best-in-class", "cutting-edge", "revolutionary", etc.
   - Is fewer than 5 words (too short to be a specific, testable claim).

Note: verb-pattern detection is intentionally absent.  It blocked legitimate
nominalized domain claims ("GPS pinning accuracy within 5 meters") while
accepting articulate-but-empty fluff ("The system is good" — copula + adjective).
Subtle vacuousness judgment belongs to the LLM concept judge (SP3).

These rules exist because concept_claims are the testable hypotheses that the
concept judge (SP3) will score.  A non-falsifiable claim cannot be judged.

## Inputs

- **`spec_path`** — path to the unified spec YAML (e.g. `docs/walkthroughs/<feature>.yaml`).
  The why_brief (if declared) is resolved automatically from the spec file's
  `why_brief` field relative to the spec file — no separate path argument needed.

## Procedure

### Step 1 — Run the QA module

```bash
python -m scripts.ddd.spec_qa <spec_path>
```

The module exits 0 on pass, 1 on fail, 2 on usage error.  Capture stdout/stderr
to display to the user.

### Step 2 — Parse and report the verdict

The module prints one of:

**Pass:**
```
spec_qa: pass
```

**Fail:**
```
spec_qa: fail
  blocking_reason: <semicolon-separated list of violations>
  fix_recommendation: <guidance>
```

Report the verdict verbatim.  The Verdict object shape is:

```yaml
schema_version: 1
dimensions: {}           # empty for QA (no LLM scoring)
overall_score: 1.0       # 1.0 on pass, 0.0 on fail
verdict: pass | fail
blocking_reason: <null on pass, string on fail>
fix_recommendation: <null on pass, string on fail>
```

### Step 3 — On pass: hand off to concept judge

If `verdict: pass`, tell the user:

```
ddd-spec-qa: PASS
Next step: run /ddd-concept-judge to score concept_claims against the walkthrough.
```

### Step 4 — On fail: guide the fix

If `verdict: fail`, display the `blocking_reason` and `fix_recommendation`.
Tell the user to fix the issues in the spec file and re-run `/ddd-spec-qa`.

**Common fixes by violation type:**

- `concept_claim is empty` → write a specific, observable outcome for this scene.
- `concept_claim is not falsifiable` → remove banned phrases and ensure the claim
  is at least 5 words; write a specific, testable outcome
  (e.g. "Users can filter tasks by status and see only open items").
- `scene references undefined persona` → add the persona to `personas` or fix the
  scene's `persona` key.
- `provenance ... does not match any SpineItem.id` → update the provenance to
  match a valid spine id from the linked why_brief.
- `why_brief declared but not resolvable` → fix the relative path or supply
  `why_brief_path` explicitly.

Do NOT proceed to the concept judge if this QA returns `verdict: fail`.
