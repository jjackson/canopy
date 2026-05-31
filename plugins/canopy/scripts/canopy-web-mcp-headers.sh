#!/usr/bin/env bash
# headersHelper for the canopy-web remote MCP server.
#
# Claude Code runs this at MCP connect time and reads a JSON object of
# header key/value pairs from stdout (10s timeout). We emit the bearer
# auth header from the per-user PAT that `/canopy:canopy-web-pat-mint`
# writes to ~/.claude/canopy/workbench-token — so there is no env var to
# export and no token in any config file. Re-minting rotates the token
# automatically (this runs fresh on each connect).
#
# If the token file is missing/empty we emit no auth header; canopy-web
# then returns 401 and /mcp surfaces the server as needing auth — the cue
# to run /canopy:canopy-web-pat-mint.
set -euo pipefail

TOKEN_FILE="${CANOPY_WORKBENCH_TOKEN:-$HOME/.claude/canopy/workbench-token}"

if [ -s "$TOKEN_FILE" ]; then
  # Strip a trailing newline; JSON-escape nothing else (PATs are url-safe base64).
  token="$(tr -d '\n' < "$TOKEN_FILE")"
  printf '{"Authorization":"Bearer %s"}' "$token"
else
  printf '{}'
fi
