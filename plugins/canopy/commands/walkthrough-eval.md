---
description: Run walkthrough eval suite — score fixtures against ground truth, track accuracy metrics, compare runs. Use when asked to "eval the walkthrough", "run walkthrough eval", or "walkthrough-eval".
argument-hint: [run|run <fixture>|history|compare <r1> <r2>|consistency <fixture>]
allowed-tools: [Read, Bash, Write, Edit, Glob, Grep, AskUserQuestion, Agent, Skill]
---

# Walkthrough Eval

Run the walkthrough eval suite to measure scoring accuracy.

## Arguments

- `run` — Run all fixtures, report metrics
- `run <fixture>` — Run a single fixture
- `history` — Show metric trends over time
- `compare <r1> <r2>` — Side-by-side comparison of two runs
- `consistency <fixture>` — Run same fixture 3x, measure variance

## Process

Read the walkthrough-eval SKILL.md and follow it:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/walkthrough-eval/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
