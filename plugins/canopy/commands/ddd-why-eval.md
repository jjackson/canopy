---
description: LLM-as-judge eval for a why_brief.yaml — scores 5 dimensions (problem_clarity, rationale_soundness, evidence_sufficiency, gap_honesty, user_narrative_strength) against the bundled rubric. Gated by ddd-why-qa. Emits pass | warn | fail verdict.
argument-hint: [<why_brief_path> [<evidence_inventory_path>]]
allowed-tools: [Read, Write, Bash]
---

# DDD Why-Brief Eval

LLM-as-judge: score a why_brief.yaml against the 5-dimension rubric.

## Arguments

- `<why_brief_path>` — path to `why_brief.yaml`.
- `<evidence_inventory_path>` — optional path to `evidence-inventory.md` (improves scoring quality).

## Process

Read the ddd-why-eval SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-why-eval/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
