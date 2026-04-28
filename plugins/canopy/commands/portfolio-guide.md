---
description: Generate "what to do next" guides for each project and upload them to canopy-web
allowed-tools: [Bash, Read, Write]
---

# Portfolio Guide

Read the portfolio-guide SKILL.md from disk and follow it exactly:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/portfolio-guide/SKILL.md')"
```

Read that file with the Read tool and follow it step by step. **Do NOT improvise from memory.** The SKILL.md is the authoritative source.
