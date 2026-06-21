---
name: update
description: Update the canopy plugin to the latest version from GitHub
---

# Update Canopy

**This is a rigid, scripted skill. Run the bash blocks EXACTLY as written. Do NOT
explore, ls, glob, read files, or improvise. The scripts below are the complete
procedure — there is nothing else to discover.**

## Step 1: Fast version check (ONE command)

Reads the remote VERSION via `git fetch` against the local marketplace clone —
uncached, unlike `raw.githubusercontent.com` (CDN-cached 1–5 min, which would
spuriously report `UP_TO_DATE` right after a push). Completes in ~1–3s
(dominated by the network fetch). The script prints exactly one line.

```bash
bash "$(sed -n '/"canopy@canopy"/,/\]/{ s/.*"installPath": *"\([^"]*\)".*/\1/p; }' "$HOME/.claude/plugins/installed_plugins.json" | head -1)/scripts/canopy-update-check.sh"
```

**Read the single output line:**
- `UP_TO_DATE <version>` → Tell the user "Already up to date at **vX.Y.Z**." and **STOP. Do nothing else.**
- `UPGRADE_AVAILABLE <old> <new>` → Continue to Step 2.
- `ERROR <reason>` → Show the error to the user and **STOP**.

## Step 2: Pull, install, and register (ONE command)

Run this single bash command. Replace `NEW_VERSION` with the remote version
from Step 1:

```bash
NEW_VERSION=<version from step 1> && \
cd ~/.claude/plugins/marketplaces/canopy && \
echo "PULLING: git pull origin main" && \
git pull origin main 2>&1 && \
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
- `VERIFIED` → continue to Step 3 (the plugin cache is updated; the CLI still needs deploying).
- `MISMATCH` → Tell the user the update failed and show the mismatch. **Do not run Step 3.**

## Step 3: Deploy the CLI (ONE command) — canopy is a plugin AND a CLI

The `canopy` *command* is the Python package (`src/orchestrator/`), NOT in the plugin cache. It
must be deployed too, from the SAME marketplace clone the plugin came from, so the CLI and plugin
always ship together from `main` (never an editable dev-checkout, which silently drifts with
whatever branch is checked out — that bug stranded `canopy harvest` from a fresh session).

```bash
uv tool install --force "$HOME/.claude/plugins/marketplaces/canopy" 2>&1 | tail -3 && \
  canopy --help >/dev/null 2>&1 && echo "CLI DEPLOYED: $(canopy --version 2>/dev/null || echo ok)" \
  || echo "CLI DEPLOY FAILED — run: uv tool install --force ~/.claude/plugins/marketplaces/canopy"
```

- `CLI DEPLOYED` → Tell the user: "Updated canopy to **vX.Y.Z** (plugin + CLI, verified). Run `/reload-plugins` to activate the plugin."
- `CLI DEPLOY FAILED` → show the error; the plugin updated but the CLI didn't (commands like `canopy harvest` may be stale).

## Rules

- The CLI is **non-editable**, installed from the marketplace clone — NEVER an editable install of
  `~/emdash-projects/canopy` (that couples `canopy` to your dev branch). For CLI dev, `uv run` from a worktree.

- **Run EXACTLY the bash blocks above.** No exploring, no ls, no reading files, no globbing.
- Always pull from `~/.claude/plugins/marketplaces/canopy` — NEVER from `~/emdash-projects/canopy`
- If Step 1 says UP_TO_DATE, STOP immediately. Do not run Step 2 **or Step 3** (CLI already current).
- Step 3 (CLI deploy) runs on every real update — the plugin and CLI ship together.
- Always tell the user to run `/reload-plugins` after a successful update.
