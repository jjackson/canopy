---
description: Re-apply the SwiftShader WebGL patch to gstack browse (fixes headless Mapbox/three.js render; re-run after gstack updates)
allowed-tools: [Bash, Read]
---

# Patch gstack browse for headless WebGL

Read the patch-gstack-browse SKILL.md from disk and follow it exactly:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/patch-gstack-browse/SKILL.md')"
```

Read that file with the Read tool and run its bash block. The SKILL.md is the
authoritative source for the idempotent patch + rebuild + verify sequence.
**Do NOT improvise from memory.**
