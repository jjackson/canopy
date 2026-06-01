#!/usr/bin/env bash
# canopy-update-check — fast version check via git fetch (uncached).
#
# Output: exactly one line, one of:
#   UP_TO_DATE <version>
#   UPGRADE_AVAILABLE <local> <remote>
#   ERROR <reason>
#
# What it does:
#   1. Read installed canopy version from ~/.claude/plugins/installed_plugins.json
#      using sed (avoiding python3 startup overhead).
#   2. Read the remote VERSION via `git fetch` + `git show origin/main:VERSION`
#      against the local marketplace clone.
#   3. Compare; print result; exit.
#
# Why git fetch instead of curl raw.githubusercontent.com:
#   raw.githubusercontent.com is CDN-cached ~1–5 minutes. Right after a push it
#   can serve the PREVIOUS version — a still-valid X.Y.Z — so a regex check
#   passes and the tool reports UP_TO_DATE falsely. That window is the common
#   case for canopy, whose documented flow is "merge, then /canopy:update
#   immediately." `git fetch` hits GitHub's git smart-HTTP endpoint, which is
#   not CDN-cached and reflects refs essentially immediately. The ~1s extra
#   latency over a curl is imperceptible for an interactive command, and Step 2
#   of the update needs this same marketplace checkout anyway (it `git pull`s
#   it), so requiring it here just surfaces a broken checkout one step earlier.
set -u

MARKETPLACE="${CANOPY_MARKETPLACE:-$HOME/.claude/plugins/marketplaces/canopy}"
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

# ─── 2. Remote version (git fetch — uncached, no CDN) ────────
if [ ! -d "$MARKETPLACE/.git" ]; then
  echo "ERROR marketplace_missing"
  exit 0
fi

git -C "$MARKETPLACE" fetch --quiet origin main 2>/dev/null
REMOTE="$(git -C "$MARKETPLACE" show origin/main:VERSION 2>/dev/null | tr -d '[:space:]')"

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
