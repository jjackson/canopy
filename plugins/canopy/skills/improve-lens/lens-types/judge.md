# Judge Lens Type

You are running canopy's **judge lens type** against a target project. Your job: identify rubric-quality issues in the project's eval skills (skills that grade producer artifacts), draft rubric edits that fix them, and return a structured findings + proposals report. The dispatcher will run your verification protocol and ship PRs.

This is the *type* — the generic implementation. Per-project specialization (which evidence sources, which file patterns, which thresholds) comes from the project's `.canopy/lenses/judge.yaml` descriptor passed in below.

## Inputs (provided by the dispatcher)

- **Project path**: absolute path to the target project's local checkout.
- **Run scope**: a `run_id` for `per_run` lenses; `null` for opp-level.
- **Lens descriptor**: parsed contents of `<project>/.canopy/lenses/judge.yaml` — project-specific signals, thresholds, file patterns, auto-merge conditions.
- **Run-artifacts descriptor**: parsed contents of `<project>/.canopy/run-artifacts.yaml` — what the project produces, which backend (gdrive / local-fs / other), which read/list tools.
- **Cross-model evidence**: dict keyed by verdict path with cross-model verdicts collected by the dispatcher's `cross_model` probe (Phase 3a). May be empty if no signal in the descriptor needs it.
- **Holistic evidence**: dict keyed by verdict path with adversarial-read output from the dispatcher's `holistic_adversarial` probe (Phase 3a). Contains top concerns, demand_reality, budget_consistency, technical_feasibility, $10K-bet odds, and explicit `rubric_blind_spots` enumeration. May be empty if no signal needs it.
- **Opp/scope binding**: any project-specific scope identifiers (e.g. `opp_name` for ACE) bound at dispatch time.
- **Max proposals**: hard cap on proposals to draft.

## Backend abstraction

This lens type is backend-agnostic. The run-artifacts descriptor declares:

```yaml
backend: gdrive | local_fs | ...
backend_config:
  read_tool: <fully-qualified tool name>
  list_tool: <fully-qualified tool name>
  ...
```

When you read or list project artifacts, dispatch the tool the descriptor names — don't hardcode a specific MCP. For `gdrive` backend the dispatcher exposes the gdrive MCP tools; for `local_fs` use the standard `Read` and `Glob`.

## Process

### Step 1 — Walk the run's verdicts

Using the `list_tool` declared in run-artifacts.yaml's `backend_config`, traverse the path matching `run_artifacts.per_run.verdicts.glob` with `{run_id}` substituted. For each verdict file, read it via `read_tool` and capture:

- The verdict file path/id
- The eval skill name (from the verdict's `skill:` field)
- The capture_path (the artifact that was judged)
- The current overall_score, dimension scores, auto_surfaced concerns

If no verdicts exist for this run, return early with `findings: []` and `[INFO]`: "no eval verdicts in this run; nothing for judge lens to analyze."

### Step 2 — Read cross-model verdicts (signal `rubric_ambiguity`)

The dispatcher has already run the cross-model variance probe (Phase 3a in `skills/improve-lens/SKILL.md`) — Agents can't dispatch Agents, so multi-model probes happen at the dispatcher level. The dispatcher passes you a `cross_model_evidence` dict in your input, keyed by verdict path:

```yaml
cross_model_evidence:
  <verdict_path>:
    sonnet: { overall_score: ..., dimensions: {...}, auto_surfaced: [...] }
    opus:   { overall_score: ..., dimensions: {...}, auto_surfaced: [...] }
    haiku:  { overall_score: ..., dimensions: {...}, auto_surfaced: [...] }
```

For each dimension, compute:
- mean across the three models
- variance (max - min, or stdev — pick one and stick with it)

Flag dimensions where variance ≥ the descriptor's threshold (default 1.0) as **rubric_ambiguity** findings. Cite the specific per-model scores in your evidence.

If `cross_model_evidence` is empty (dispatcher skipped probing — typically because all verdicts had score < 6 and routed to the production lens), surface `[INFO]: no cross-model probes ran for this verdict set` and proceed to other signal detectors.

### Step 3 — Inflation guard probe (signal `inflation_guard_binds`)

Read the verdict's `overall_score_pre_cap` and `overall_score`. If the gap is ≥ 0.5 (descriptor threshold), flag as **inflation_guard_binds**. The rubric's score-cap rule is doing work — the rubric is producing scores high enough to need capping, which means the dimension-level deductions are too lenient.

### Step 4 — Dimension distribution probe (signal `dimension_inert`)

Across the three cross-model verdicts plus the original verdict (4 data points), compute per-dimension stdev. If stdev < 0.5 AND the score is in [7, 10] (consistently high) OR in [0, 4] (consistently low), the dimension isn't discriminating — flag as **dimension_inert**.

### Step 5 — Surface-vs-score correlation probe (signal `auto_surfaced_unscored`)

For each `auto_surfaced` entry with severity WARN or BLOCKER:
- Identify which dimension it should have penalized (use rubric semantics or the original verdict's per-item notes).
- If that dimension's score is ≥ 8 in all four verdicts (original + 3 cross-model), flag as **auto_surfaced_unscored** — the rubric is surfacing a concern but not deducting for it.

### Step 6 — Rubric blind-spot probe (signal `rubric_blind_spot`)

This is the most important signal — it catches cases where the rubric isn't asking the right questions. Cross-model variance and inflation guards measure rubric *internal consistency*; this signal measures rubric *scope*.

The dispatcher passes you `holistic_evidence` keyed by verdict path:

```yaml
holistic_evidence:
  <verdict_path>:
    top_concerns:
      - severity: critical|high|medium|low
        concern: "..."
        rubric_caught_it: yes|no   # would the existing rubric catch this?
    overall_viability_score: <0-10 — adversarial read of program viability>
    rubric_blind_spots: ["named blind spot 1", "named blind spot 2", ...]
    ten_k_bet:
      odds_youd_take: "..."
```

Compute the **gap** between the rubric's score and the holistic viability score:

- `rubric_score` = original verdict's `overall_score`
- `holistic_score` = `holistic_evidence[verdict].overall_viability_score`
- `gap = rubric_score - holistic_score`

Flag as **rubric_blind_spot** finding when:
- `gap ≥ 2.0` (the rubric is grading 2+ points higher than an adversarial read), OR
- `holistic_evidence.top_concerns` includes ≥1 entry with `severity: critical` AND `rubric_caught_it: no`, OR
- `holistic_evidence.rubric_blind_spots` enumerates ≥3 named gaps not addressable by tightening any existing dimension.

**Severity inference:**
- `gap ≥ 4.0` OR ≥2 critical-severity concerns the rubric missed → **high severity finding**
- `gap ∈ [2.0, 4.0)` OR 1 critical-severity concern missed → **medium severity finding**
- Otherwise → low

The remediation for this signal is **adding new dimensions to the rubric** (and re-weighting existing ones), not tightening anchors. This is structurally different from the other 4 signals in this lens — it expands the rubric rather than refining it.

If `holistic_evidence` is empty (dispatcher skipped the probe), surface `[INFO]: no holistic probe ran; rubric_blind_spot signal not evaluated this run` and proceed.

### Step 7 — Rank findings, cap to max-proposals

Sort findings by severity (high > medium > low) then by signal strength (variance for ambiguity, gap for inflation, etc.). Take the top N where N = max-proposals.

For each surviving finding, draft a candidate rubric edit:

- **rubric_ambiguity**: tighten the dimension's anchor language. Specify what tier of defect maps to what deduction value with named examples. Reduce ambiguity that lets models drift.
- **inflation_guard_binds**: lower the dimension's full-pass anchor (e.g. raise the bar from 9.5 to 9.0 for "all comments addressed"), OR add a deduction rule for a defect class the rubric was missing.
- **dimension_inert**: either raise the deduction stakes (make the dimension actually capable of failing) or reduce its weight (it isn't pulling its weight).
- **auto_surfaced_unscored**: add a deduction rule that ties the surfaced concern to a dimension drop. e.g. "if `[WARN] X` is surfaced, the X-related dimension must score ≤ 7."
- **rubric_blind_spot**: ADD a new dimension to the rubric. For each blind spot named in holistic_evidence, propose a dimension with: name, weight (must rebalance — weights must still sum to 1.0; steal from over-weighted document-quality dimensions), and clear anchor scoring rules. Use the holistic evidence's specific concerns as the anchor examples (e.g. "absent named downstream consumer = score ≤ 4; named consumer with implicit commitment = 6-7; named consumer with explicit pre-committed action = 9-10").

**Proposed-edit format** (for each proposal):

```yaml
target_file: "skills/<eval-skill>/SKILL.md"
target_section: "## LLM-as-Judge Rubric"
edit_type: text_replacement
old_text: |
  <exact substring from current rubric, ≤ 30 lines>
new_text: |
  <replacement text, same anchor structure>
rationale: |
  <2-3 sentences explaining why this edit addresses the finding>
```

**Constraints from the descriptor's `proposes:` block:**
- Edits must target only `skills/<eval-skill>/SKILL.md` and only the `## LLM-as-Judge Rubric` section.
- Don't rename the skill, don't change dimension weights' total (must still sum to 1.0), don't delete dimensions.

### Step 7 — Return findings + proposals

Return a single YAML report:

```yaml
findings:
  - id: <12-char hex>
    signal: <signal-id>
    target_skill: <eval-skill name>
    target_artifact: <capture_path>
    severity: low|medium|high
    description: |
      <what's wrong with the rubric, with evidence>
    evidence:
      cross_model_verdicts:    # if applicable
        sonnet: { overall: ..., dim1: ..., ... }
        opus: { overall: ..., dim1: ..., ... }
        haiku: { overall: ..., dim1: ..., ... }
      original_verdict_path: <verdict YAML path>
      pre_cap_vs_post_cap:    # if applicable
        pre: ...
        post: ...

proposals:
  - id: <12-char hex>
    finding_id: <id>
    target_file: "skills/<eval-skill>/SKILL.md"
    target_section: "## LLM-as-Judge Rubric"
    edit_type: text_replacement
    old_text: |
      ...
    new_text: |
      ...
    rationale: |
      ...
    estimated_impact: |
      <expected change in score / variance / detection — used by dispatcher to evaluate against pass_criteria>

skipped_findings:
  - <id>
    reason: "previous proposal for same (lens, target_file, signal) was tried and failed verification — see proposal <prior-id>"

stats:
  verdicts_analyzed: N
  cross_model_probes_run: N
  findings_total: N
  proposals_drafted: N
  proposals_skipped: N
```

The dispatcher takes this report, runs the `re_grade` verification protocol on each proposal (apply edit in memory → re-dispatch eval against the same artifact → compare verdicts), and ships PRs for proposals that pass.

## Important notes

- **Don't run the producer.** The judge lens NEVER regenerates artifacts. If a finding seems to require regenerating the artifact to verify, it's not a judge-lens finding — note it as `cross_lens_referral: production` so the dispatcher can hand it to the production lens later.
- **Don't propose if a previous proposal failed.** Check `~/.claude/canopy/proposals/` for prior `(lens=judge, target_file, signal)` tuples in status `failed_verification`. Skip those — wait for new evidence before retrying.
- **Stay inside the rubric section.** The descriptor's `proposes.edit_targets[].section: "## LLM-as-Judge Rubric"` is a hard boundary. If the right fix is somewhere else (Process steps, Inputs, etc.), that's not a judge fix — it's a producer fix; refer to production lens.
- **Cross-model probe is the bite.** Without it, you're guessing at rubric ambiguity from a single verdict. Always run the probe before flagging `rubric_ambiguity`.
