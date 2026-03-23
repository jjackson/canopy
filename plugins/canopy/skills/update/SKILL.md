---
name: update
description: Update the canopy plugin to the latest version from GitHub
version: 0.1.0
---

# Update Canopy

Pull the latest canopy plugin from GitHub and refresh the local cache.

## Flow

### Step 1: Pull latest from GitHub

```bash
cd ~/.claude/plugins/marketplaces/canopy && git pull origin main
```

If this fails (e.g. directory doesn't exist), tell the user the canopy marketplace is not installed and stop.

### Step 2: Copy to plugin cache

```bash
cp -r ~/.claude/plugins/marketplaces/canopy/plugins/canopy/* ~/.claude/plugins/cache/canopy/canopy/0.1.0/
cp -r ~/.claude/plugins/marketplaces/canopy/plugins/canopy/.claude-plugin ~/.claude/plugins/cache/canopy/canopy/0.1.0/
```

### Step 3: Show what changed

Run from the marketplace directory:

```bash
cd ~/.claude/plugins/marketplaces/canopy && git log --oneline -5
```

Show the recent commits so the user knows what updated.

### Step 4: Confirm

Tell the user the plugin is updated. New skills and commands will be available in the next Claude Code session. If they want changes to take effect in the current session, they need to restart.

## Rules

- Always pull before copying to cache
- If git pull shows "Already up to date", say so and skip the copy step
- Do not modify any files in the marketplace or cache directories beyond the copy
