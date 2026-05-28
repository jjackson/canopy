---
description: LLM-as-judge concept eval for a rendered walkthrough — scores 5 dimensions (concept_clarity, design_soundness, why_groundedness, claim_reality_coherence, motion_friction) against the bundled rubric. Gated by ddd-spec-qa. Dispatches canopy:visual-judge per scene. Emits verdict-concept.yaml + design_findings.json.
argument-hint: [<run_dir> [<unified_spec_path> [<why_brief_path>]]]
allowed-tools: [Read, Write, Bash, Skill, Agent]
---

# DDD Concept Eval

LLM-as-judge: score a rendered walkthrough against the 5-dimension concept rubric.
Measures whether the product concept is sound — not visual polish.

## Arguments

- `<run_dir>` — path to the rendered walkthrough run dir (contains scene screenshots + page text JSON).
- `<unified_spec_path>` — optional explicit path to `unified_spec.yaml` (default: `<run_dir>/unified_spec.yaml`).
- `<why_brief_path>` — optional explicit path to `why_brief.yaml` (default: `<run_dir>/why_brief.yaml`).

## Process

Read the ddd-concept-eval SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-concept-eval/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
