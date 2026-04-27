---
description: Update the canopy plugin to the latest version from GitHub
allowed-tools: [Bash, Read]
---

# Update Canopy

Read the update SKILL.md from disk and follow it exactly:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/update/SKILL.md')"
```

Read that file with the Read tool and follow it step by step. The SKILL.md contains the rigid two-step procedure (fast version check, then pull/install/register). **Do NOT improvise from memory.** The SKILL.md is the authoritative source.
