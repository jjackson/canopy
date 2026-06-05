---
description: Author a unified spec (docs/walkthroughs/<narrative-slug>.yaml) from a validated why_brief.yaml — one scene per spine item with concept_claim, provenance, and design_intent. Output is both a design doc and a runnable canopy walkthrough spec. Loops until validate passes.
argument-hint: [<why_brief_path> [<base_url>]]
allowed-tools: [Read, Write, Bash, Edit]
---

# DDD Unified Spec

Author a unified spec that is simultaneously a design doc and a runnable canopy walkthrough spec.

## Arguments

- `<why_brief_path>` — path to the validated `why_brief.yaml`.
  If not supplied, looks for `.canopy/ddd/<narrative-slug>/why_brief.yaml` for the most recent run.
- `<base_url>` — the live environment URL to target (e.g. `https://labs.connect.dimagi.com`).

## Process

Read the ddd-spec SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-spec/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
