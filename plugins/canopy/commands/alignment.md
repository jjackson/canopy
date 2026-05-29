---
description: Compare two sibling systems for drift and post reasoned findings to the canopy-web /insights feed — alignment <projectA> <projectB>
allowed-tools: [Bash, Read, Agent]
---

# Alignment

Read the alignment SKILL.md from disk and follow it exactly:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/alignment/SKILL.md')"
```

Read that file with the Read tool and follow it step by step. **Do NOT improvise from memory.** The SKILL.md is the authoritative source.

The two project slugs to align are passed as arguments to this command: $ARGUMENTS
