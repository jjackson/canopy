---
name: doctor
description: Diagnose canopy plugin health — workbench token, repo-map, session log, hook registration, and skill connectivity.
---

# Doctor

Check that the canopy plugin is correctly configured and can communicate with the workbench.

## Checks

Run each check in order. Report results as a table at the end.

### 1. Hook registration

Verify the PostToolUse hook is registered in Claude Code settings:

```bash
python3 -c "
import json, sys
from pathlib import Path

settings = Path.home() / '.claude' / 'settings.json'
if not settings.exists():
    print('FAIL: ~/.claude/settings.json not found')
    sys.exit(0)

data = json.load(open(settings))
hooks = data.get('hooks', {}).get('PostToolUse', [])
found = any(
    'post_tool_use.py' in h.get('command', '')
    for entry in hooks
    for h in entry.get('hooks', [])
)
print('OK: PostToolUse hook registered' if found else 'FAIL: PostToolUse hook not registered — run /canopy:setup')
"
```

### 1b. Hook Python compatibility

The hook runs under whatever `python3` is on the user's PATH — often the
Xcode CLT default `python3.9` on macOS, not the project venv. A 3.10+-only
annotation in hook code (`str | None` PEP 604 union syntax, etc.) compiles
fine in CI under the project venv but silently no-ops on real user
machines. Catch that locally:

```bash
SYS_PY=$(command -v python3)
PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
HOOK_DIR=""
for cand in \
  "$HOME/.claude/plugins/marketplaces/canopy/hooks" \
  "$HOME/emdash/repositories/canopy/hooks" \
  "$HOME/emdash-projects/canopy/hooks"; do
  [ -d "$cand" ] && HOOK_DIR="$cand" && break
done

if [ -z "$HOOK_DIR" ]; then
  echo "WARN: could not locate hooks dir — skipping compat check"
else
  FAILED=""
  for f in "$HOOK_DIR"/*.py; do
    [ -f "$f" ] || continue
    if ! "$SYS_PY" -m py_compile "$f" 2>/dev/null; then
      FAILED="$FAILED $(basename "$f")"
    fi
  done
  if [ -z "$FAILED" ]; then
    echo "OK: hooks compile under $SYS_PY ($PY_VER)"
  else
    echo "FAIL: hooks fail to compile under $SYS_PY ($PY_VER):$FAILED"
    echo "  Fix: rewrite the incompatible syntax to support the system python."
    echo "  This is the same class of bug as commit 7c13988 (str | None under 3.9)."
    echo "  CI workflow .github/workflows/hook-compat.yml is the upstream gate."
  fi
fi
```

### 2. Session log

```bash
LOG=~/.claude/canopy/session-log.jsonl
if [ -f "$LOG" ]; then
  LINES=$(wc -l < "$LOG")
  SIZE=$(du -h "$LOG" | cut -f1)
  echo "OK: session-log.jsonl exists ($LINES entries, $SIZE)"
else
  echo "WARN: session-log.jsonl not found — hook may not be firing"
fi
```

### 3. Repo map

```bash
MAP=~/.claude/canopy/repo-map.json
if [ -f "$MAP" ]; then
  COUNT=$(python3 -c "import json; print(len(json.load(open('$MAP'))))")
  echo "OK: repo-map.json has $COUNT project mappings"
else
  echo "WARN: repo-map.json not found — project identification won't work"
fi
```

### 4. Workbench token

```bash
# Check CLAUDE_PLUGIN_DATA path first, then fallback
TOKEN_FILE=""
if [ -n "$CLAUDE_PLUGIN_DATA" ] && [ -f "$CLAUDE_PLUGIN_DATA/workbench-token" ]; then
  TOKEN_FILE="$CLAUDE_PLUGIN_DATA/workbench-token"
elif [ -f "$HOME/.claude/canopy/workbench-token" ]; then
  TOKEN_FILE="$HOME/.claude/canopy/workbench-token"
fi

if [ -z "$TOKEN_FILE" ]; then
  echo "FAIL: workbench-token not found at ~/.claude/canopy/workbench-token"
  echo "  Fix: run /canopy:setup (handles GCP fetch + permissions automatically)"
else
  PERMS=$(stat -f "%Lp" "$TOKEN_FILE" 2>/dev/null || stat -c "%a" "$TOKEN_FILE" 2>/dev/null)
  LEN=$(wc -c < "$TOKEN_FILE" | tr -d ' ')
  if [ "$PERMS" = "600" ]; then
    echo "OK: workbench-token exists ($LEN bytes, permissions $PERMS)"
  else
    echo "WARN: workbench-token exists but permissions are $PERMS (should be 600)"
    echo "  Fix: chmod 600 $TOKEN_FILE"
  fi
fi
```

### 5. Workbench API connectivity

Test that the token works against the live API:

```bash
API_URL="${CANOPY_WEB_API_URL:-https://canopy-web-ujpz2cuyxq-uc.a.run.app}"

if [ -z "$TOKEN_FILE" ]; then
  echo "SKIP: no token to test with"
else
  TOKEN=$(cat "$TOKEN_FILE")
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
    -X POST "$API_URL/api/projects/canopy-web/actions/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"skill_name":"canopy:doctor","status":"completed","started_at":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'","session_id":"doctor-check"}')

  if [ "$HTTP_CODE" = "201" ]; then
    echo "OK: workbench API accepts token (HTTP $HTTP_CODE)"
  elif [ "$HTTP_CODE" = "401" ]; then
    echo "FAIL: workbench API rejected token (HTTP 401) — token may be stale or mismatched"
    echo "  Fix: re-download from GCP: gcloud secrets versions access latest --secret=workbench-write-token > ~/.claude/canopy/workbench-token"
  elif [ "$HTTP_CODE" = "000" ]; then
    echo "FAIL: workbench API unreachable (timeout) — is $API_URL running?"
  else
    echo "WARN: workbench API returned HTTP $HTTP_CODE (expected 201)"
  fi
fi
```

### 6. Plugin version

```bash
python3 -c "
import json
from pathlib import Path
f = Path.home() / '.claude' / 'plugins' / 'installed_plugins.json'
if not f.exists():
    print('WARN: installed_plugins.json not found')
else:
    data = json.load(open(f))
    for key, val in data.get('plugins', {}).items():
        if 'canopy' in key:
            entries = val if isinstance(val, list) else [val]
            if entries:
                print(f'OK: canopy {entries[0].get(\"version\", \"unknown\")}')
"
```

### 7. Auth checks

Run the auth preflight to surface stale GitHub, 1Password, or AWS SSO
credentials. Treat results as informational here — auth-preflight failures do
not change overall canopy plugin health, but they're worth reporting so the
user can fix them before a deploy. The same checks are also available
standalone via `canopy:auth-preflight`.

```bash
bash scripts/canopy-auth-preflight.sh || true
```

## Report

After running all checks, present a summary table:

```
Check                 Status
─────────────────     ──────
Hook registration     OK
Hook py compat        OK (compiles under python3.9)
Session log           OK (1234 entries, 5.8M)
Repo map              OK (42 mappings)
Workbench token       OK (43 bytes, 600)
API connectivity      OK (HTTP 201)
Plugin version        OK (canopy 0.2.31)
```

If any check is FAIL, highlight the fix command. If all pass, say "All checks passed — canopy is healthy."
