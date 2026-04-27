---
description: Re-entry survey for "where do I stand on this project?" — current branch, worktrees, open PRs, recent merges, stale branches
allowed-tools: [Bash, Read]
---

# Project Status

Read the project-status SKILL.md from disk and follow it exactly:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/project-status/SKILL.md')"
```

Read that file with the Read tool and follow it. The SKILL.md describes when
to use the survey and how to present the output. **Do NOT improvise from
memory.** The SKILL.md is the authoritative source.
