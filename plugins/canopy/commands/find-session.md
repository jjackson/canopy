---
description: Find your OTHER active Claude Code session on a repo and digest what it's doing — branch, recent commits, recent prompts, dirty files. Excludes the current session.
allowed-tools: [Bash, Read]
---

# Find Session

Read the find-session SKILL.md from disk and follow it exactly:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/find-session/SKILL.md')"
```

Read that file with the Read tool and follow it. The SKILL.md describes when to
use the lookup, how to invoke the helper, and how to present the digest. **Do
NOT improvise from memory.** The SKILL.md is the authoritative source.

The user's target (if any) is: $ARGUMENTS
