---
description: One-shot idempotent setup for the canopy plugin on a new machine — state dir, main checkout, hook, workbench token, CLI
allowed-tools: [Bash]
---

# Canopy Setup

Run the canonical setup script from the installed plugin. The script is
idempotent — already-completed steps print `OK` and are skipped.

```bash
PLUGIN_PATH=$(python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'])")
bash "$PLUGIN_PATH/scripts/canopy-setup.sh"
```

Report the script's output verbatim so the user sees each step's status. If
any step fails, the script prints the exact remediation; surface that to the
user and offer to re-run `/canopy:setup` after the fix.

After a successful run, remind the user to:
1. Restart Claude Code so the PostToolUse hook starts firing
2. Run `/canopy:doctor` to verify workbench API connectivity
