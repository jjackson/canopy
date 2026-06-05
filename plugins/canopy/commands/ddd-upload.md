---
description: Upload a converged DDD run's artifacts to canopy-web as one navigable package — upload the hero video, build the self-contained HTML docs page (deck), run the external_release gate, and publish so the video + deck + narrative + links group at /ddd/<narrative-slug>/<run_id> (phase → uploaded). Returns the package URL, not a loose artifact link.
argument-hint: <run_id> --video <video_path>
allowed-tools: [Read, Write, Bash, Skill]
---

# DDD Upload

Uploads a converged DDD run's artifacts to canopy-web so they package together
under the run — a single navigable view (video, deck, narrative, links) at
`/ddd/<narrative-slug>/<run_id>`.

## Arguments

- `<run_id>` — converged run identifier.
- `--video <video_path>` — path to the hero video `.mp4`.

## Process

Read the ddd-upload SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-upload/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
