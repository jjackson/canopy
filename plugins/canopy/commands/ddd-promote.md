---
description: Promote a converged DDD run (SP7) — upload the hero video, build the self-contained HTML docs page (hero video + capabilities + why + how for a prospective user), run the external_release gate, and publish to canopy-web (phase → promoted).
argument-hint: <run_id> --video <video_path>
allowed-tools: [Read, Write, Bash, Skill]
---

# DDD Promote — SP7

Publishes the terminal artifact of a converged DDD run: a documentation page
for prospective users of the feature.

## Arguments

- `<run_id>` — converged run identifier.
- `--video <video_path>` — path to the hero video `.mp4`.

## Process

Read the ddd-promote SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-promote/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
