---
description: Audit a Python/pytest test suite and (by default) open a PR pruning dumb tests
allowed-tools: [Read, Bash]
---

# Test Audit

Read the test-audit SKILL.md from disk and follow it:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/test-audit/SKILL.md')"
```

Read that file with the Read tool and follow it step by step. **Do NOT improvise from memory.** The SKILL.md is the authoritative source.
