---
description: Full demo-driven-development (DDD) v2 orchestrator — bootstraps from .canopy/ddd/context.md + learnings.md, runs Phase 0 (evidence-audit → why-brief → why-qa → why-eval), drafts + QA-gates a unified spec (ddd-spec → ddd-spec-qa), renders and dual-judges it (ddd-run → ddd-concept-eval + visual-judge), routes PRODUCT / CONCEPT / RESEARCH / CAPABILITY findings to fixers, and converges toward promotion. Two pause gates only: concept_change and external_release.
argument-hint: [<feature>] [--resume <run_id>]
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, Skill, Agent, AskUserQuestion]
---

# DDD — Demo-Driven Development v2

Orchestrate the full DDD loop for a feature from raw evidence to a converged
concept verdict and stakeholder-ready walkthrough.

## Arguments

- `<feature>` — feature slug (e.g. `rooftop-sampling`). If omitted, reads from
  `.canopy/ddd/context.md` or asks.
- `--resume <run_id>` — resume an existing run instead of starting a new one.

## Process

Read the ddd agent definition and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/agents/ddd.md')"
```

Read that file with the Read tool and follow it step by step.

## Pause gates

Only two gates ever pause and await human input:

1. **concept_change** — concept redefinition, DECISION gaps, or a finding that
   requires changing what the product does.
2. **external_release** — publishing the walkthrough to external stakeholders.

Everything else runs autonomously and is reported in the digest.
