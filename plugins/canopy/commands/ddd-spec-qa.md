---
description: Run pure-python structural QA on a unified spec YAML — delegates provenance/persona/schema checks to validate(), adds falsifiability check on every concept_claim (no banned marketing phrases, must have a verb). Returns pass | fail verdict. Gates the concept judge.
argument-hint: [<spec_path> [<why_brief_path>]]
allowed-tools: [Read, Bash]
---

# DDD Unified Spec QA

Structural gate: validate a unified spec before running the concept judge.

## Arguments

- `<spec_path>` — path to the unified spec YAML (e.g. `docs/walkthroughs/<feature>.yaml`).
  If not supplied, looks for the most recent spec in `docs/walkthroughs/`.
- `<why_brief_path>` *(optional)* — explicit path to the why_brief if it is
  not resolvable from the spec file's `why_brief` field.

## Process

Read the ddd-spec-qa SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-spec-qa/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
