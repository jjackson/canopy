---
description: Generate walkthrough eval fixtures by injecting calibrated defects into a clean HTML page. Use when asked to "create walkthrough fixtures", "generate eval fixtures", or "walkthrough-defect-creator".
argument-hint: <source-name>
allowed-tools: [Read, Bash, Write, Edit, Glob, Grep, AskUserQuestion]
---

# Walkthrough Defect Creator

Generate eval fixtures from a clean source page.

## Arguments

- `<source-name>` — Name of the source in `evals/walkthrough/source/<name>/`

## Process

Read the walkthrough-defect-creator SKILL.md and follow it:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/walkthrough-defect-creator/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
