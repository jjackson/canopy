---
name: update
description: Update the canopy plugin to the latest version from GitHub
---

# Update Canopy

**This is a rigid, scripted skill. Run the bash blocks EXACTLY as written. Do NOT
explore, ls, glob, read files, or improvise. The scripts below are the complete
procedure — there is nothing else to discover.**

## Step 1: Pull and compare (ONE command)

Run this single bash command. Do NOT split it up or run anything before it:

```bash
cd ~/.claude/plugins/marketplaces/canopy && git pull origin main 2>&1 && python3 -c "
import json, subprocess, sys, os

home = os.path.expanduser('~')

# Read installed version
with open(f'{home}/.claude/plugins/installed_plugins.json') as f:
    installed = json.load(f)
entry = installed.get('plugins', {}).get('canopy@canopy', [{}])[0]
iv = entry.get('version', 'unknown')
sha = entry.get('gitCommitSha', 'unknown')[:8]

# Read marketplace version
with open(f'{home}/.claude/plugins/marketplaces/canopy/plugins/canopy/.claude-plugin/plugin.json') as f:
    marketplace = json.load(f)
mv = marketplace['version']

# Recent commits
log = subprocess.run(['git', 'log', '--oneline', '-5'], capture_output=True, text=True).stdout.strip()

print(f'Installed: v{iv} ({sha})')
print(f'GitHub:    v{mv}')
print(f'')
print(log)
print(f'')
if iv == mv:
    print('STATUS: UP_TO_DATE')
else:
    print(f'STATUS: UPGRADE_AVAILABLE {iv} {mv}')
"
```

**Read the STATUS line at the end of the output:**
- `UP_TO_DATE` → Tell the user "Already up to date at **vX.Y.Z**." and **STOP. Do nothing else.**
- `UPGRADE_AVAILABLE <old> <new>` → Continue to Step 2.

If the `cd` or `git pull` fails, tell the user the canopy marketplace is not installed and **STOP**.

## Step 2: Install and update (ONE command)

Run this single bash command. Replace `NEW_VERSION` with the version from Step 1:

```bash
NEW_VERSION=<version from step 1> && \
mkdir -p ~/.claude/plugins/cache/canopy/canopy/$NEW_VERSION && \
rsync -a ~/.claude/plugins/marketplaces/canopy/plugins/canopy/ ~/.claude/plugins/cache/canopy/canopy/$NEW_VERSION/ && \
cd ~/.claude/plugins/marketplaces/canopy && python3 -c "
import json, subprocess, os
from datetime import datetime, timezone

home = os.path.expanduser('~')
version = '$NEW_VERSION'
cache_path = f'{home}/.claude/plugins/cache/canopy/canopy/{version}'
sha = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')

path = f'{home}/.claude/plugins/installed_plugins.json'
with open(path) as f:
    data = json.load(f)

entries = data.get('plugins', {}).get('canopy@canopy', [{}])
entries[0]['version'] = version
entries[0]['installPath'] = cache_path
entries[0]['gitCommitSha'] = sha
entries[0]['lastUpdated'] = now

with open(path, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')

# Verify
with open(path) as f:
    check = json.load(f)
cv = check['plugins']['canopy@canopy'][0]['version']
with open(f'{home}/.claude/plugins/marketplaces/canopy/plugins/canopy/.claude-plugin/plugin.json') as f:
    mv = json.load(f)['version']

if cv == mv:
    print(f'VERIFIED: v{cv} installed and matches GitHub')
else:
    print(f'MISMATCH: installed v{cv} but GitHub has v{mv}')
"
```

**Read the output:**
- `VERIFIED` → Tell the user exactly: "Updated canopy to **vX.Y.Z** (verified against GitHub). Run `/reload-plugins` to activate."
- `MISMATCH` → Tell the user the update failed and show the mismatch.

## Rules

- **Run EXACTLY the two bash blocks above.** No exploring, no ls, no reading files, no globbing.
- Always pull from `~/.claude/plugins/marketplaces/canopy` — NEVER from `~/emdash-projects/canopy`
- If Step 1 says UP_TO_DATE, STOP immediately. Do not run Step 2.
- Always tell the user to run `/reload-plugins` after a successful update.
