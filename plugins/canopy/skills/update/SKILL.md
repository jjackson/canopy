---
name: update
description: Update the canopy plugin to the latest version from GitHub
version: 0.4.0
---

# Update Canopy

Pull the latest canopy plugin from GitHub and install it into the plugin cache.

**IMPORTANT:** Always pull from `~/.claude/plugins/marketplaces/canopy` (the marketplace
repo), NOT from `~/emdash-projects/canopy` (the source repo). The source repo may be
up to date but the plugin cache won't be — the marketplace repo feeds the cache.

## Flow

### Step 1: Pull latest from the MARKETPLACE repo

```bash
cd ~/.claude/plugins/marketplaces/canopy && git pull origin main
```

If this fails (e.g. directory doesn't exist), tell the user the canopy marketplace
is not installed and stop.

### Step 2: Read the new version from the marketplace

```bash
cat ~/.claude/plugins/marketplaces/canopy/plugins/canopy/.claude-plugin/plugin.json
```

Extract the `version` field (e.g. `0.2.6`).

### Step 3: Check current installed version

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['version'])"
```

If the installed version matches the marketplace version, say "Already up to date
at version X" and stop.

### Step 4: Install to cache

Create the new cache directory and copy the plugin contents:

```bash
NEW_VERSION=<version from step 2>
mkdir -p ~/.claude/plugins/cache/canopy/canopy/$NEW_VERSION
rsync -a ~/.claude/plugins/marketplaces/canopy/plugins/canopy/ ~/.claude/plugins/cache/canopy/canopy/$NEW_VERSION/
```

### Step 5: Update installed_plugins.json

Update the `canopy@canopy` entry in `~/.claude/plugins/installed_plugins.json`:
- Set `version` to the new version
- Set `installPath` to the new cache directory
- Set `gitCommitSha` to the current HEAD of the marketplace repo
- Set `lastUpdated` to the current timestamp

```bash
cd ~/.claude/plugins/marketplaces/canopy && git rev-parse HEAD
```

Use python3 to read, update, and write the JSON file.

### Step 6: Verify and report

Read back `installed_plugins.json` and confirm the version matches what the
marketplace has:

```bash
python3 -c "
import json
installed = json.load(open('$HOME/.claude/plugins/installed_plugins.json'))
marketplace = json.load(open('$HOME/.claude/plugins/marketplaces/canopy/plugins/canopy/.claude-plugin/plugin.json'))
iv = installed['plugins']['canopy@canopy'][0]['version']
mv = marketplace['version']
match = 'VERIFIED' if iv == mv else 'MISMATCH'
print(f'Installed: {iv}  |  Marketplace: {mv}  |  {match}')
"
```

Show the recent commits:
```bash
cd ~/.claude/plugins/marketplaces/canopy && git log --oneline -5
```

Then output EXACTLY this message (fill in the version):

```
Updated canopy to **X.Y.Z** (verified against GitHub).
Run `/reload-plugins` to activate.
```

## Why this flow

`/reload-plugins` only reloads skill definitions from the existing cache directory.
It does NOT detect version changes or re-install from the marketplace. Only a new
session does that automatically. This update skill bridges the gap by doing the
install step, then `/reload-plugins` picks up the new cache.

## Rules

- **Always pull from `~/.claude/plugins/marketplaces/canopy`** — never the source repo
- Always create a new cache dir for the new version (don't overwrite old ones)
- Always update installed_plugins.json so Claude Code knows the current version
- Always verify the installed version matches the marketplace version at the end
- Always tell the user to run `/reload-plugins`
- If already up to date, say the version number so the user can confirm
