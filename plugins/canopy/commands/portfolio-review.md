---
description: Generate categorized portfolio insights — one feed across all projects, scannable and actionable
allowed-tools: [Bash, Read, Write]
---

# Portfolio Review

Read the portfolio-review SKILL.md from disk and follow it exactly:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/portfolio-review/SKILL.md')"
```

Read that file with the Read tool and follow it step by step. **Do NOT improvise from memory.** The SKILL.md is the authoritative source.
