---
description: Run pure-python structural QA on a unified spec YAML — delegates provenance/persona/schema checks to validate(), adds falsifiability check on every concept_claim (no banned marketing phrases, minimum 5 words). Returns pass | fail verdict. Gates the concept judge.
argument-hint: [<spec_path>]
allowed-tools: [Read, Bash]
---

# DDD Unified Spec QA

Structural gate: validate a unified spec before running the concept judge.

## Arguments

- `<spec_path>` — path to the unified spec YAML (e.g. `docs/walkthroughs/<feature>.yaml`).
  If not supplied, looks for the most recent spec in `docs/walkthroughs/`.
  The why_brief (if declared) is resolved automatically from the spec's `why_brief`
  field — no separate path argument is needed.

## Process

Read the ddd-spec-qa SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-spec-qa/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
