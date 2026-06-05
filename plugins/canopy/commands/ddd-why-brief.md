---
description: Draft a why-brief (why_brief.yaml) from the evidence inventory produced by ddd-evidence-audit. Builds a grounded narrative spine; unsupported claims become typed Gaps (RESEARCH / CAPABILITY / DECISION). Loops until the validator passes.
argument-hint: [<run_dir>]
allowed-tools: [Read, Write, Bash, Edit]
---

# DDD Why-Brief

Transform an evidence inventory into a validated why_brief.yaml.

## Arguments

- `<run_dir>` — directory containing `evidence.json` and where `why_brief.yaml` will be written.
  If not supplied, defaults to `.canopy/ddd/<narrative-slug>/` for the most recent ddd-evidence-audit run.

## Process

Read the ddd-why-brief SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-why-brief/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
