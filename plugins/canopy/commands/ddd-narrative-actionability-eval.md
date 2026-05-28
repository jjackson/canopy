---
description: Narrative actionability eval — cold-derives a build plan from each scene's narration (NOT its features[]), runs ~3 independent derivations for self-consistency, then scores coverage/specificity/correctness/consistency against the declared features[]. Gated by ddd-spec-qa. Emits verdict-actionability.yaml + actionability_findings[].
argument-hint: [<unified_spec_path>]
allowed-tools: [Read, Write, Bash, Skill, Agent]
---

# DDD Narrative Actionability Eval

Cold-derive then score: can a builder independently infer what to build from the narration alone?

## Arguments

- `<unified_spec_path>` — path to `unified_spec.yaml` (contains scenes with narration, concept_claim, show, features[]).

## Process

Read the ddd-narrative-actionability-eval SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-narrative-actionability-eval/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
