#!/usr/bin/env bash
# Resolve $CANOPY_DDD_DIR for the current cwd.
#
# Inside a git repo: <repo-root>/.canopy/ddd
# Outside a git repo: $HOME/.canopy/ddd/<basename-of-cwd>
#
# Stdout: the resolved path (created if it doesn't exist).
# Stderr: human-readable notes, if any.

set -euo pipefail

if REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
  CANOPY_DDD_DIR="$REPO_ROOT/.canopy/ddd"
else
  CANOPY_DDD_DIR="$HOME/.canopy/ddd/$(basename "$(pwd)")"
fi

mkdir -p "$CANOPY_DDD_DIR"
echo "$CANOPY_DDD_DIR"
