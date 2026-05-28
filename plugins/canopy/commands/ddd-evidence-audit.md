---
description: Audit evidence for a DDD feature — gather docs, code, and research; classify as documented | implemented | assumed; write evidence-inventory.md + evidence.json into the run dir. Use at the start of a DDD Phase 0 cycle.
argument-hint: [<feature_name> [<run_dir>]]
allowed-tools: [Read, Write, Glob, Grep, Bash, Agent]
---

# DDD Evidence Audit

Gather and classify evidence for a named feature before drafting the why-brief.

## Arguments

- `<feature_name>` — name of the feature to audit (e.g. "Rooftop Survey Sampling")
- `<run_dir>` — optional output directory (default: `.canopy/ddd/<feature_name>/`)

## Process

Read the ddd-evidence-audit SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-evidence-audit/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
