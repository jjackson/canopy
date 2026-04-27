---
description: Generate a strategic brief from recent canopy activity
allowed-tools: [Read, Bash]
---

# Brief

Read the brief SKILL.md from disk and follow it:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/brief/SKILL.md')"
```

Read that file with the Read tool and follow it step by step. **Do NOT improvise from memory.** The SKILL.md is the authoritative source.
