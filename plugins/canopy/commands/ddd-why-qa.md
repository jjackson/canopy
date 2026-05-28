---
description: Run pure-python structural QA on a why_brief.yaml — checks non-empty problem, non-empty rationale, grounded items have real evidence, Gap.claim_refs resolve. Returns pass | fail verdict. Gates ddd-why-eval.
argument-hint: [<why_brief_path>]
allowed-tools: [Read, Bash]
---

# DDD Why-Brief QA

Structural gate: validate why_brief.yaml before running the LLM eval.

## Arguments

- `<why_brief_path>` — path to `why_brief.yaml`.
  If not supplied, looks for `.canopy/ddd/<feature>/why_brief.yaml` for the most recent run.

## Process

Read the ddd-why-qa SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-why-qa/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
