#!/usr/bin/env bash
# canopy-update-check — lightweight version check for canopy plugin.
#
# Output (one line, or nothing):
#   UPGRADE_AVAILABLE <installed> <remote>  — remote version differs
#   (nothing)                               — up to date or check skipped
#
# Runs in <100ms when cached (checks GitHub at most once per hour).
set -euo pipefail

STATE_DIR="$HOME/.canopy"
CACHE_FILE="$STATE_DIR/last-update-check"
INSTALLED_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"
REMOTE_URL="https://raw.githubusercontent.com/jjackson/canopy/main/plugins/canopy/.claude-plugin/plugin.json"
CACHE_TTL=3600  # seconds (1 hour)

# ─── Step 1: Get installed version ────────────────────────────
if [ ! -f "$INSTALLED_PLUGINS" ]; then
  exit 0
fi

LOCAL=$(python3 -c "
import json
try:
    d = json.load(open('$INSTALLED_PLUGINS'))
    print(d['plugins']['canopy@canopy'][0]['version'])
except (KeyError, IndexError, FileNotFoundError):
    print('unknown')
" 2>/dev/null || echo "unknown")

if [ "$LOCAL" = "unknown" ]; then
  exit 0
fi

# ─── Step 2: Check cache ─────────────────────────────────────
mkdir -p "$STATE_DIR"
if [ -f "$CACHE_FILE" ]; then
  CACHE_AGE=$(( $(date +%s) - $(stat -f %m "$CACHE_FILE" 2>/dev/null || stat -c %Y "$CACHE_FILE" 2>/dev/null || echo 0) ))
  if [ "$CACHE_AGE" -lt "$CACHE_TTL" ]; then
    CACHED=$(cat "$CACHE_FILE")
    case "$CACHED" in
      UPGRADE_AVAILABLE*)
        echo "$CACHED"
        ;;
    esac
    exit 0
  fi
fi

# ─── Step 3: Fetch remote version ────────────────────────────
REMOTE_JSON=$(curl -sf --max-time 5 "$REMOTE_URL" 2>/dev/null || true)
if [ -z "$REMOTE_JSON" ]; then
  echo "UP_TO_DATE $LOCAL" > "$CACHE_FILE"
  exit 0
fi

REMOTE=$(echo "$REMOTE_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['version'])" 2>/dev/null || true)

if [ -z "$REMOTE" ]; then
  echo "UP_TO_DATE $LOCAL" > "$CACHE_FILE"
  exit 0
fi

if [ "$LOCAL" = "$REMOTE" ]; then
  echo "UP_TO_DATE $LOCAL" > "$CACHE_FILE"
  exit 0
fi

echo "UPGRADE_AVAILABLE $LOCAL $REMOTE" > "$CACHE_FILE"
echo "UPGRADE_AVAILABLE $LOCAL $REMOTE"
