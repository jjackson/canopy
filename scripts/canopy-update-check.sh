#!/usr/bin/env bash
# canopy-update-check — lightweight version check for canopy plugin.
#
# Output (one line, or nothing):
#   UPGRADE_AVAILABLE <installed> <remote>  — remote version differs
#   (nothing)                               — up to date or check skipped
#
# Pure bash + curl, no Python. Fetches a single VERSION file (~10 bytes).
set -euo pipefail

STATE_DIR="$HOME/.canopy"
CACHE_FILE="$STATE_DIR/last-update-check"
INSTALLED_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"
REMOTE_URL="https://raw.githubusercontent.com/jjackson/canopy/main/VERSION"
CACHE_TTL=0  # seconds (check every time — set to 3600 once stable)

# ─── Step 1: Get installed version ────────────────────────────
if [ ! -f "$INSTALLED_PLUGINS" ]; then
  exit 0
fi

# Extract version with grep/sed — no Python needed
LOCAL=$(grep -o '"canopy@canopy"' "$INSTALLED_PLUGINS" >/dev/null 2>&1 && \
  sed -n '/"canopy@canopy"/,/\]/{ s/.*"version": *"\([^"]*\)".*/\1/p; }' "$INSTALLED_PLUGINS" | head -1 || echo "unknown")

if [ -z "$LOCAL" ] || [ "$LOCAL" = "unknown" ]; then
  exit 0
fi

# ─── Step 2: Check cache ─────────────────────────────────────
mkdir -p "$STATE_DIR"
if [ -f "$CACHE_FILE" ] && [ "$CACHE_TTL" -gt 0 ]; then
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

# ─── Step 3: Fetch remote VERSION file ────────────────────────
REMOTE=$(curl -sf --max-time 5 "$REMOTE_URL" 2>/dev/null | tr -d '[:space:]' || true)

if [ -z "$REMOTE" ]; then
  echo "UP_TO_DATE $LOCAL" > "$CACHE_FILE"
  exit 0
fi

# Validate: must look like a version number
if ! echo "$REMOTE" | grep -qE '^[0-9]+\.[0-9.]+$'; then
  echo "UP_TO_DATE $LOCAL" > "$CACHE_FILE"
  exit 0
fi

if [ "$LOCAL" = "$REMOTE" ]; then
  echo "UP_TO_DATE $LOCAL" > "$CACHE_FILE"
  exit 0
fi

echo "UPGRADE_AVAILABLE $LOCAL $REMOTE" > "$CACHE_FILE"
echo "UPGRADE_AVAILABLE $LOCAL $REMOTE"
