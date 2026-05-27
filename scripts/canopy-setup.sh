#!/usr/bin/env bash
# canopy-setup.sh
#
# One-shot, idempotent setup for the canopy plugin on a new machine.
# Each step prints its own pass/skip/fail line. Safe to re-run.
#
# Steps:
#   1. ~/.claude/canopy/ state dir (session-log + repo-map will land here)
#   2. ~/emdash-projects/canopy/ main checkout (stable path used by emdash worktrees + CLI)
#   3. PostToolUse hook registered in ~/.claude/settings.json
#      (registered to point at the main-checkout path so it survives plugin updates)
#   4. workbench-token from GCP Secret Manager (or via /canopy:canopy-web-pat-mint)
#   5. canopy CLI installed from main checkout
#
# Exit code: 0 if all required steps pass, 1 otherwise.
# Stdlib bash + python3 only; no plugin dependencies.

set -u

CANOPY_STATE_DIR="$HOME/.claude/canopy"
MAIN_CHECKOUT="$HOME/emdash-projects/canopy"
SETTINGS_FILE="$HOME/.claude/settings.json"
TOKEN_FILE="$CANOPY_STATE_DIR/workbench-token"
REPO_URL="https://github.com/jjackson/canopy.git"

FAILED=0
NEXT_STEPS=()  # Lines appended here are printed as a remediation block at the end.

echo "=== Canopy setup ==="
echo

# ---------- 1. State dir ----------
if [ -d "$CANOPY_STATE_DIR" ]; then
  echo "[1/5] state dir       : OK ($CANOPY_STATE_DIR)"
elif mkdir -p "$CANOPY_STATE_DIR"; then
  echo "[1/5] state dir       : CREATED ($CANOPY_STATE_DIR)"
else
  echo "[1/5] state dir       : FAIL — could not create $CANOPY_STATE_DIR"
  FAILED=1
fi

# ---------- 2. Main checkout ----------
if [ -d "$MAIN_CHECKOUT/.git" ]; then
  echo "[2/5] main checkout   : OK ($MAIN_CHECKOUT)"
else
  if ! command -v git >/dev/null 2>&1; then
    echo "[2/5] main checkout   : FAIL — git not installed"
    FAILED=1
  else
    mkdir -p "$(dirname "$MAIN_CHECKOUT")"
    if git clone --quiet "$REPO_URL" "$MAIN_CHECKOUT" 2>/dev/null; then
      echo "[2/5] main checkout   : CLONED ($MAIN_CHECKOUT)"
    else
      echo "[2/5] main checkout   : FAIL — \`git clone $REPO_URL $MAIN_CHECKOUT\` failed"
      FAILED=1
    fi
  fi
fi

# ---------- 3. Hook registration ----------
hook_already_registered() {
  python3 - <<'PY' 2>/dev/null
import json, sys
from pathlib import Path
s = Path.home() / ".claude" / "settings.json"
if not s.exists():
    sys.exit(1)
d = json.load(open(s))
hooks = d.get("hooks", {}).get("PostToolUse", [])
found = any(
    "post_tool_use.py" in h.get("command", "")
    for entry in hooks
    for h in entry.get("hooks", [])
)
sys.exit(0 if found else 1)
PY
}

if hook_already_registered; then
  echo "[3/5] post-tool hook  : OK (already registered)"
elif [ -f "$MAIN_CHECKOUT/hooks/install.py" ]; then
  if python3 "$MAIN_CHECKOUT/hooks/install.py" >/dev/null 2>&1; then
    echo "[3/5] post-tool hook  : REGISTERED → $MAIN_CHECKOUT/hooks/post_tool_use.py"
  else
    echo "[3/5] post-tool hook  : FAIL — $MAIN_CHECKOUT/hooks/install.py errored"
    FAILED=1
  fi
else
  echo "[3/5] post-tool hook  : SKIP — $MAIN_CHECKOUT/hooks/install.py missing (step 2 must succeed first)"
  FAILED=1
fi

# ---------- 4. Workbench token ----------
if [ -s "$TOKEN_FILE" ]; then
  PERMS=$(stat -f "%Lp" "$TOKEN_FILE" 2>/dev/null || stat -c "%a" "$TOKEN_FILE" 2>/dev/null)
  if [ "$PERMS" != "600" ]; then
    chmod 600 "$TOKEN_FILE"
  fi
  echo "[4/5] workbench token : OK ($TOKEN_FILE)"
elif ! command -v gcloud >/dev/null 2>&1; then
  echo "[4/5] workbench token : FAIL — gcloud SDK not installed"
  NEXT_STEPS+=(
    "Install Google Cloud SDK and re-run /canopy:setup:"
    "  brew install --cask google-cloud-sdk"
    "  gcloud auth login"
    "  gcloud config set project <your-canopy-project>"
  )
  FAILED=1
elif ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | grep -q .; then
  echo "[4/5] workbench token : FAIL — no active gcloud credentials"
  NEXT_STEPS+=(
    "Authenticate gcloud and re-run /canopy:setup:"
    "  gcloud auth login"
    "  gcloud config set project <your-canopy-project>  # if not already set"
  )
  FAILED=1
elif [ -z "$(gcloud config get-value project 2>/dev/null)" ]; then
  echo "[4/5] workbench token : FAIL — gcloud project not configured"
  NEXT_STEPS+=(
    "Set the gcloud project (the one that owns the workbench-write-token secret) and re-run /canopy:setup:"
    "  gcloud config set project <your-canopy-project>"
  )
  FAILED=1
elif gcloud secrets versions access latest --secret=workbench-write-token > "$TOKEN_FILE" 2>/dev/null && [ -s "$TOKEN_FILE" ]; then
  chmod 600 "$TOKEN_FILE"
  echo "[4/5] workbench token : FETCHED from GCP Secret Manager"
else
  rm -f "$TOKEN_FILE"
  PROJECT=$(gcloud config get-value project 2>/dev/null)
  echo "[4/5] workbench token : FAIL — secret access denied (project: $PROJECT)"
  NEXT_STEPS+=(
    "gcloud is authed and project is set ($PROJECT), but \`workbench-write-token\` access failed."
    "Either the secret lives in a different project, or your account lacks Secret Manager Accessor."
    "Fix one of:"
    "  gcloud config set project <correct-project>   # then re-run /canopy:setup"
    "  # or grant your account roles/secretmanager.secretAccessor on the secret"
  )
  FAILED=1
fi

# ---------- 5. canopy CLI ----------
# Editable install needs a modern PEP 660 build backend. macOS system pip3
# (from Xcode CLT) is too old, so we use uv (preferred) or pipx. If neither
# is installed, we install uv automatically via the official installer.
ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    return 1
  fi
  # Progress goes to stderr — install_cli is called inside $(...) so stdout is captured.
  echo "      uv not found — installing via https://astral.sh/uv/install.sh ..." >&2
  if curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1; then
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    command -v uv >/dev/null 2>&1
  else
    return 1
  fi
}

install_cli() {
  local target="$1"
  if command -v pipx >/dev/null 2>&1; then
    if pipx install --force -e "$target" >/dev/null 2>&1; then
      echo "pipx"
      return 0
    fi
  fi
  if ensure_uv; then
    if uv tool install --force --editable "$target" >/dev/null 2>&1; then
      echo "uv tool"
      return 0
    fi
  fi
  return 1
}

if command -v canopy >/dev/null 2>&1; then
  echo "[5/5] canopy CLI      : OK ($(command -v canopy))"
elif [ -f "$MAIN_CHECKOUT/pyproject.toml" ]; then
  METHOD=$(install_cli "$MAIN_CHECKOUT") || true
  if [ -n "${METHOD:-}" ] && command -v canopy >/dev/null 2>&1; then
    echo "[5/5] canopy CLI      : INSTALLED via $METHOD ($(command -v canopy))"
  elif [ -n "${METHOD:-}" ]; then
    echo "[5/5] canopy CLI      : INSTALLED via $METHOD — but \`canopy\` not on current PATH"
    NEXT_STEPS+=(
      "Add ~/.local/bin to your shell PATH so the \`canopy\` CLI is reachable:"
      "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
      "  source ~/.zshrc   # or open a new terminal"
    )
    FAILED=1
  else
    echo "[5/5] canopy CLI      : FAIL — uv install failed and no pipx fallback"
    NEXT_STEPS+=(
      "Install uv (or pipx) manually and re-run /canopy:setup:"
      "  brew install uv     # recommended"
      "  # or: brew install pipx"
    )
    FAILED=1
  fi
else
  echo "[5/5] canopy CLI      : SKIP — main checkout missing (step 2 must succeed first)"
  FAILED=1
fi

# Note: /canopy:walkthrough-share now uses the same ~/.claude/canopy/workbench-token
# PAT covered by step 4 (mint via /canopy:canopy-web-pat-mint). No separate
# step here — one token, multiple consumers (hook + walkthrough-share +
# canopy-doctor).

echo
if [ "$FAILED" -eq 0 ]; then
  echo "All checks passed. Restart Claude Code so the new PostToolUse hook fires,"
  echo "then run /canopy:canopy-doctor to verify the API connection."
else
  echo "=== Next steps ==="
  for line in "${NEXT_STEPS[@]}"; do
    echo "$line"
  done
  echo
  echo "After fixing the items above, re-run \`/canopy:setup\` — it's idempotent and skips completed steps."
fi

exit "$FAILED"
