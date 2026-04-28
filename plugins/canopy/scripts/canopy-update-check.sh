#!/usr/bin/env bash
# canopy-update-check — single fast HTTP pull, no caching.
#
# Output: exactly one line, one of:
#   UP_TO_DATE <version>
#   UPGRADE_AVAILABLE <local> <remote>
#   ERROR <reason>
#
# What it does:
#   1. Read installed canopy version from ~/.claude/plugins/installed_plugins.json
#      using sed (avoiding python3 startup overhead).
#   2. curl one ~10-byte VERSION file from GitHub raw.
#   3. Compare; print result; exit.
#
# That's it. No cache, no TTL, no state directory. Designed for:
#   - frequent /canopy:update invocations (canopy is shipping changes constantly)
#   - speed (~200ms typical, dominated by the single curl)
#   - clarity (the script does ONE thing)
#
# Falls back to `gh api` only if the curl response isn't a valid version
# string — typically because raw.githubusercontent.com's CDN lags a few
# minutes after a fresh push.
set -u

REMOTE_URL="${CANOPY_REMOTE_URL:-https://raw.githubusercontent.com/jjackson/canopy/main/VERSION}"
INSTALLED_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"

# ─── 1. Installed version ────────────────────────────────────
if [ ! -f "$INSTALLED_PLUGINS" ]; then
  echo "ERROR registry_missing"
  exit 0
fi

# Pull "version" out of the canopy@canopy entry without parsing the whole JSON.
LOCAL="$(sed -n '/"canopy@canopy"/,/\]/{ s/.*"version": *"\([^"]*\)".*/\1/p; }' \
  "$INSTALLED_PLUGINS" 2>/dev/null | head -1)"

if [ -z "$LOCAL" ]; then
  echo "ERROR no_local_version"
  exit 0
fi

# ─── 2. Remote version (single HTTP pull) ────────────────────
REMOTE="$(curl -sf --max-time 5 "$REMOTE_URL" 2>/dev/null | tr -d '[:space:]')"

# CDN lag fallback — only if curl didn't return a valid version.
if ! echo "$REMOTE" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  if command -v gh >/dev/null 2>&1; then
    REMOTE="$(gh api 'repos/jjackson/canopy/contents/VERSION' --jq .content 2>/dev/null \
      | base64 -d 2>/dev/null | tr -d '[:space:]')"
  fi
fi

if ! echo "$REMOTE" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "ERROR fetch_failed"
  exit 0
fi

# ─── 3. Compare ──────────────────────────────────────────────
if [ "$LOCAL" = "$REMOTE" ]; then
  echo "UP_TO_DATE $LOCAL"
else
  echo "UPGRADE_AVAILABLE $LOCAL $REMOTE"
fi
