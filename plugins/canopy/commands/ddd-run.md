---
description: Render + dual-verdict run (SP4) — gates on ddd-spec-qa, invokes canopy:walkthrough to render the unified_spec, dispatches ddd-concept-eval + canopy:visual-judge (audience=feature user) in parallel, assembles both verdicts into run_state.yaml, and reports convergence.
argument-hint: <run_id> <unified_spec_path> <why_brief_path>
allowed-tools: [Read, Write, Bash, Skill, Agent]
---

# DDD Run — Render + Dual-Verdict

Orchestrates the SP4 render-then-judge sequence: spec QA gate → render via
canopy:walkthrough → parallel concept + user-artifact judges → assemble into
run_state → convergence report.

## Arguments

- `<run_id>` — run identifier from `scripts.ddd.runstate.new_run`.
- `<unified_spec_path>` — path to `unified_spec.yaml` (runnable walkthrough spec).
- `<why_brief_path>` — path to `why_brief.yaml`.

## Process

Read the ddd-run SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-run/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
