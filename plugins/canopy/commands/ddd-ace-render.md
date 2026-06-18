---
description: Render a DDD narrative as a narrated connect-ddd-walkthrough video on demand — record a fresh master clip, emit the explainer spec, and hand off to the local ace renderer. Standalone; not the auto loop, does not publish.
argument-hint: <narrative-slug> [--run=<run-NNN>]
allowed-tools: [Read, Write, Bash, Skill]
---

# /canopy:ddd-ace-render

Turn one DDD narrative into a narrated `connect-ddd-walkthrough` MP4:
**record** a fresh master clip, **emit** the explainer spec (canopy), and
**hand off** to the local ace renderer (`/ace:video-render-local`). On
demand — not part of `/canopy:ddd-run`, and it does not publish.

## Arguments
- `<narrative-slug>` — the narrative whose spec lives at `docs/walkthroughs/<slug>.yaml` in the current project repo.
- `--run=<run-NNN>` — optional connect-videos run id for the staged program (default `run-001`).

## Process

Read the ddd-ace-render SKILL.md and follow it step by step:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-ace-render/SKILL.md')"
```

Read that file with the Read tool and follow it: resolve the spec + canopy
scripts, record a fresh master clip, emit the explainer spec via
`scripts.ddd.snippets explainer-from-capture`, then invoke
`/ace:video-render-local` (Mode A) with the emitted spec + clip. Report the
output MP4 path and the timing report; flag a large held-frame overrun so the
user can trim the narration before shipping.
