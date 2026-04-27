---
description: Show cross-session friction patterns — recurring issues and project hotspots
allowed-tools: [Read, Bash]
---

# Patterns

Read the patterns SKILL.md from disk and follow it:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/patterns/SKILL.md')"
```

Read that file with the Read tool and follow it step by step. **Do NOT improvise from memory.** The SKILL.md is the authoritative source.
