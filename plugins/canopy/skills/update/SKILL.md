---
name: update
description: Update the canopy plugin to the latest version from GitHub
version: 0.2.0
---

# Update Canopy

Pull the latest canopy plugin from GitHub and activate it.

## Flow

### Step 1: Pull latest and install

```bash
cd ~/.claude/plugins/marketplaces/canopy && git pull origin main
```

If this fails (e.g. directory doesn't exist), tell the user the canopy marketplace is not installed and stop.

If git pull shows "Already up to date", say so and skip to Step 3.

### Step 2: Show what changed

```bash
cd ~/.claude/plugins/marketplaces/canopy && git log --oneline -5
```

Show the recent commits so the user knows what updated.

### Step 3: Activate

Tell the user to run `/reload-plugins` to activate the changes in the current session. This is required — without it, new or updated skills won't be available until the next session.

## Rules

- Always pull before anything else
- Do not manually copy files to the cache — `/reload-plugins` handles that
- If already up to date, just say so and skip the reload prompt
