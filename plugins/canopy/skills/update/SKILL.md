---
name: update
description: Update the canopy plugin to the latest version from GitHub
version: 0.3.0
---

# Update Canopy

Pull the latest canopy plugin from GitHub and install it into the plugin cache.

## Flow

### Step 1: Pull latest from GitHub

```bash
cd ~/.claude/plugins/marketplaces/canopy && git pull origin main
```

If this fails (e.g. directory doesn't exist), tell the user the canopy marketplace
is not installed and stop.

If git pull shows "Already up to date", say so and stop.

### Step 2: Read the new version

```bash
cat ~/.claude/plugins/marketplaces/canopy/plugins/canopy/.claude-plugin/plugin.json
```

Extract the `version` field (e.g. `0.2.4`).

### Step 3: Install to cache

Create the new cache directory and copy the plugin contents:

```bash
NEW_VERSION=<version from step 2>
mkdir -p ~/.claude/plugins/cache/canopy/canopy/$NEW_VERSION
rsync -a ~/.claude/plugins/marketplaces/canopy/plugins/canopy/ ~/.claude/plugins/cache/canopy/canopy/$NEW_VERSION/
```

### Step 4: Update installed_plugins.json

Update the `canopy@canopy` entry in `~/.claude/plugins/installed_plugins.json`:
- Set `version` to the new version
- Set `installPath` to the new cache directory
- Set `gitCommitSha` to the current HEAD of the marketplace repo
- Set `lastUpdated` to the current timestamp

```bash
cd ~/.claude/plugins/marketplaces/canopy && git rev-parse HEAD
```

Use python3 to read, update, and write the JSON file.

### Step 5: Show what changed

```bash
cd ~/.claude/plugins/marketplaces/canopy && git log --oneline -5
```

### Step 6: Reload

Tell the user to run `/reload-plugins` to activate the new version.

## Why this flow

`/reload-plugins` only reloads skill definitions from the existing cache directory.
It does NOT detect version changes or re-install from the marketplace. Only a new
session does that automatically. This update skill bridges the gap by doing the
install manually, then `/reload-plugins` picks up the new cache.

## Rules

- Always pull first
- Always create a new cache dir for the new version (don't overwrite old ones)
- Always update installed_plugins.json so Claude Code knows the current version
- If already up to date, just say so
