---
name: update
description: Update the canopy plugin to the latest version from GitHub
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
[ -n "$_CANOPY_UPD" ] && echo "$_CANOPY_UPD"
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# Update Canopy

Pull the latest canopy plugin from GitHub and activate it.

## Flow

### Step 1: Show current installed version

```bash
python3 -c "
import json
with open('$HOME/.claude/plugins/installed_plugins.json') as f:
    data = json.load(f)
entry = data.get('plugins', {}).get('canopy@canopy', [{}])[0]
print(f'Installed: v{entry.get(\"version\", \"unknown\")}')
print(f'Cache: {entry.get(\"installPath\", \"unknown\")}')
print(f'Commit: {entry.get(\"gitCommitSha\", \"unknown\")[:8]}')
"
```

### Step 2: Pull latest from GitHub

```bash
cd ~/.claude/plugins/marketplaces/canopy && git pull origin main
```

If this fails (e.g. directory doesn't exist), tell the user the canopy marketplace is not installed and stop.

### Step 3: Show GitHub version and diff

```bash
python3 -c "
import json
with open('$HOME/.claude/plugins/marketplaces/canopy/plugins/canopy/.claude-plugin/plugin.json') as f:
    data = json.load(f)
print(f'GitHub: v{data[\"version\"]}')
" && cd ~/.claude/plugins/marketplaces/canopy && git log --oneline -5
```

Show the user a clear comparison:

```
Installed: v0.2.6
GitHub:    v0.2.8
```

If both versions match and git pull said "Already up to date", say so and skip to Step 4.

If versions differ, show the recent commits so the user knows what changed.

### Step 4: Activate

Tell the user to run `/reload-plugins` to activate the changes in the current session. This is required — without it, new or updated skills won't be available until the next session.

## Rules

- Always show installed vs GitHub version
- Always pull before comparing
- Do not manually copy files to the cache — `/reload-plugins` handles that
- If already up to date, just say so and skip the reload prompt
