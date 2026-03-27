# Phase 2B: Intelligence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cross-session pattern detection, strategic briefing, self-improvement tracking, and tiered routing to the improvement pipeline.

**Architecture:** Four new modules that enhance the existing pipeline's analysis and decision-making quality. Cross-session intelligence aggregates observations across projects. Strategic brief replaces the simple digest with CEO-level reporting. Self-improvement tracking logs proposal outcomes. Tiered routing classifies proposals by complexity.

**Tech Stack:** Python 3.11+, existing orchestrator modules, no new dependencies

**Spec:** `docs/superpowers/specs/2026-03-22-autonomous-convergence-ceo-plan.md`

---

## File Structure

### New files

| File | Responsibility |
|---|---|
| `src/orchestrator/patterns.py` | Cross-session pattern detection across all observations |
| `src/orchestrator/briefing.py` | Strategic brief generation with cognitive patterns |
| `src/orchestrator/tracker.py` | Self-improvement tracking — proposal outcome logging |
| `src/orchestrator/router.py` | Tiered routing — classify proposals by complexity |
| `src/orchestrator/prompts/briefing.md` | Prompt template for strategic brief |
| `tests/test_patterns.py` | Tests for cross-session patterns |
| `tests/test_briefing.py` | Tests for strategic brief |
| `tests/test_tracker.py` | Tests for self-improvement tracker |
| `tests/test_router.py` | Tests for tiered routing |

### Modified files

| File | Change |
|---|---|
| `src/orchestrator/pipeline.py` | Integrate patterns, briefing, tracker, router |
| `src/orchestrator/digest.py` | Replace with briefing module call |

---

### Task 1: Cross-Session Pattern Detection

Aggregate observations across all projects to find systemic issues and recurring workflows.

**Files:**
- Create: `src/orchestrator/patterns.py`
- Create: `tests/test_patterns.py`

The module reads all observations from disk and identifies:
- **Recurring friction** — same type of issue across multiple sessions/projects
- **Workflow patterns** — recurring multi-tool sequences
- **Project hotspots** — which projects have the most friction
- **Trend detection** — is friction increasing or decreasing over time?

Key functions:
- `detect_patterns(obs_dir) -> list[dict]` — scan all observations, return pattern list
- `find_recurring_issues(observations) -> list[dict]` — group by type+servers, rank by frequency
- `find_project_hotspots(observations) -> list[dict]` — count issues per project/repo
- `generate_trends(obs_dir, runs_dir) -> dict` — compare recent vs older observations

Each pattern has: `type`, `description`, `frequency`, `projects`, `severity`, `actionable` (bool)

- [ ] **Step 1: Write tests**
- [ ] **Step 2: Implement module**
- [ ] **Step 3: Verify tests pass**
- [ ] **Step 4: Commit**

```bash
git add src/orchestrator/patterns.py tests/test_patterns.py
git commit -m "feat: add cross-session pattern detection"
```

---

### Task 2: Strategic Brief

Replace the simple digest with a CEO-level strategic brief.

**Files:**
- Create: `src/orchestrator/briefing.py`
- Create: `src/orchestrator/prompts/briefing.md`
- Create: `tests/test_briefing.py`

The briefing module:
- Reads recent run logs, observations, proposals, and cross-session patterns
- Applies gstack cognitive patterns (inversion reflex, leverage obsession, focus as subtraction)
- Produces a markdown brief answering:
  - What happened in the last cycle?
  - What's the highest-leverage improvement to make next?
  - What should we stop doing?
  - What trends are emerging?
  - What's the overall health of the ecosystem?

Key functions:
- `generate_brief(state_dir, registry_path) -> str` — produce the full brief
- `build_brief_prompt(patterns, observations, proposals, runs) -> str` — construct the prompt
- The brief is generated via `claude -p` using the briefing prompt template

The prompt template (`briefing.md`) should embed gstack's cognitive patterns:
- Inversion reflex: "What would make us fail?"
- Leverage obsession: "What's the 10x ROI move?"
- Focus as subtraction: "What should we stop doing?"
- Proxy skepticism: "Are our metrics still serving real needs?"

- [ ] **Step 1: Write prompt template**
- [ ] **Step 2: Write tests**
- [ ] **Step 3: Implement module**
- [ ] **Step 4: Verify tests pass**
- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/briefing.py src/orchestrator/prompts/briefing.md tests/test_briefing.py
git commit -m "feat: add strategic brief with gstack cognitive patterns"
```

---

### Task 3: Self-Improvement Tracker

Log which proposals succeed and use that data to auto-tune prioritization.

**Files:**
- Create: `src/orchestrator/tracker.py`
- Create: `tests/test_tracker.py`

The tracker:
- After each cycle, records: observation_id → proposal_id → outcome (implemented/failed/pending)
- Tracks verification confidence vs actual outcome
- Computes success rates by proposal type and verification confidence level
- Provides data for future prioritization tuning

Key functions:
- `record_outcome(tracker_path, observation_id, proposal_id, outcome, evidence) -> None`
- `load_outcomes(tracker_path) -> list[dict]`
- `compute_success_rates(outcomes) -> dict` — success rate by type and confidence
- `get_prioritization_weights(outcomes) -> dict` — suggested weights based on track record

Storage: `~/.claude/canopy/tracker.jsonl` — append-only JSONL

- [ ] **Step 1: Write tests**
- [ ] **Step 2: Implement module**
- [ ] **Step 3: Verify tests pass**
- [ ] **Step 4: Commit**

```bash
git add src/orchestrator/tracker.py tests/test_tracker.py
git commit -m "feat: add self-improvement tracker for proposal outcomes"
```

---

### Task 4: Tiered Routing

Classify proposals by complexity and route to the cheapest capable execution tier.

**Files:**
- Create: `src/orchestrator/router.py`
- Create: `tests/test_router.py`

Inspired by Citadel's four-tier model, simplified to three tiers:

| Tier | Description | When | Cost |
|---|---|---|---|
| **Inline** | Simple fix, no subprocess needed | Registry update, config change | Free |
| **Single** | One `claude -p` session | New tool, tool improvement | ~$1-2 |
| **Team** | Agent team with parallel teammates | Multi-file refactor, new server | ~$5-10 |

Key functions:
- `classify_proposal(proposal) -> str` — returns "inline", "single", or "team"
- `route_proposal(proposal, config) -> dict` — returns execution plan with tier, budget, timeout

Classification rules:
- `registry_update` → inline (just edit YAML)
- `new_tool`, `tool_improvement`, `new_skill`, `hook_improvement` → single
- `new_server`, complex `new_workflow` → team
- Override: if `complexity == "low"` → inline or single. If `complexity == "high"` → team.

- [ ] **Step 1: Write tests**
- [ ] **Step 2: Implement module**
- [ ] **Step 3: Verify tests pass**
- [ ] **Step 4: Commit**

```bash
git add src/orchestrator/router.py tests/test_router.py
git commit -m "feat: add tiered routing for proposal execution"
```

---

### Task 5: Pipeline Integration

Wire all four new modules into the pipeline.

**Files:**
- Modify: `src/orchestrator/pipeline.py`

Changes:
- After analysis: run `detect_patterns()` and include in run log
- After proposals: run `classify_proposal()` on each to set execution tier
- After implementation: call `record_outcome()` for each proposal
- At report time: call `generate_brief()` instead of simple digest

- [ ] **Step 1: Update pipeline imports**
- [ ] **Step 2: Wire pattern detection after analysis**
- [ ] **Step 3: Wire router for proposal classification**
- [ ] **Step 4: Wire tracker for outcome recording**
- [ ] **Step 5: Wire briefing for reporting**
- [ ] **Step 6: Run full test suite**
- [ ] **Step 7: Commit**

```bash
git add src/orchestrator/pipeline.py
git commit -m "feat: integrate patterns, router, tracker, and briefing into pipeline"
```

---

### Task 6: Update Docs

- [ ] **Step 1: Update CLAUDE.md with new modules**
- [ ] **Step 2: Commit and push**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: update CLAUDE.md with Phase 2B intelligence modules"
```
