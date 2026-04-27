#!/usr/bin/env bash
# canopy-project-status.sh
#
# Re-entry survey for "where do I stand on this project?"
# Reports current location, branch state, worktrees, open PRs, recent merges,
# and stale branches. Read-only — never mutates anything.
#
# Designed for: returning to a project after time away, picking up after a
# context switch, or auditing a worktree's state before a risky operation.
#
# Stdlib bash + git (required) + gh (optional). Graceful when gh is missing.
# Exit code is always 0 — this is informational, not a gate.

set -u

# ---------- helpers ----------
heading() { printf '\n## %s\n' "$1"; }
note() { printf '  %s\n' "$1"; }

# ---------- 0. Confirm we're in a git repo ----------
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not in a git repository — nothing to report."
  exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
GIT_DIR="$(git rev-parse --git-dir)"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '(detached)')"
PROJECT_NAME="$(basename "$REPO_ROOT")"

case "$GIT_DIR" in
  *worktrees*) IS_WORKTREE=1 ;;
  *) IS_WORKTREE=0 ;;
esac

# Default branch (main, master, or origin/HEAD)
DEFAULT_BRANCH="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')"
if [ -z "${DEFAULT_BRANCH:-}" ]; then
  for cand in main master; do
    if git show-ref --verify --quiet "refs/heads/$cand" 2>/dev/null \
      || git show-ref --verify --quiet "refs/remotes/origin/$cand" 2>/dev/null; then
      DEFAULT_BRANCH="$cand"
      break
    fi
  done
fi
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"

# ---------- 1. Current location ----------
printf '# Project Status — %s\n' "$PROJECT_NAME"

heading "Current location"
note "Worktree: $REPO_ROOT"
note "Branch:   $BRANCH"
if [ "$IS_WORKTREE" = "1" ]; then
  note "(this is a worktree — main checkout is elsewhere)"
fi

# Ahead / behind vs default branch
if git rev-parse --verify "origin/$DEFAULT_BRANCH" >/dev/null 2>&1; then
  AHEAD="$(git rev-list --count "origin/$DEFAULT_BRANCH..HEAD" 2>/dev/null || echo '?')"
  BEHIND="$(git rev-list --count "HEAD..origin/$DEFAULT_BRANCH" 2>/dev/null || echo '?')"
  note "vs origin/$DEFAULT_BRANCH: $AHEAD ahead, $BEHIND behind"
fi

# Local mutations
DIRTY="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
STASH="$(git stash list 2>/dev/null | wc -l | tr -d ' ')"
note "Working tree: $DIRTY uncommitted changes, $STASH stash entries"

# ---------- 2. Worktrees ----------
heading "Worktrees"
git worktree list 2>/dev/null | while IFS= read -r line; do
  # Mark current
  WT_PATH="$(echo "$line" | awk '{print $1}')"
  if [ "$WT_PATH" = "$REPO_ROOT" ]; then
    printf '  %s   (current)\n' "$line"
  else
    printf '  %s\n' "$line"
  fi
done

# ---------- 3. Open PRs ----------
heading "Open PRs (this repo)"
if command -v gh >/dev/null 2>&1; then
  if gh auth status >/dev/null 2>&1; then
    PR_OUTPUT="$(gh pr list --limit 15 --state open \
      --json number,title,headRefName,isDraft,author \
      --jq '.[] | "  #\(.number)  \(.title[:60])  \(.headRefName)  \(if .isDraft then "(draft)" else "(open)" end)  by \(.author.login)"' 2>/dev/null)"
    GH_RC=$?
    if [ "$GH_RC" -ne 0 ]; then
      note "(gh pr list failed — likely not in a GitHub repo)"
    elif [ -n "$PR_OUTPUT" ]; then
      echo "$PR_OUTPUT"
    else
      note "(none)"
    fi
  else
    note "(gh not authenticated — run \`gh auth login\`)"
  fi
else
  note "(gh not installed — skipping PR check)"
fi

# ---------- 4. Recent merges ----------
heading "Recent merges to $DEFAULT_BRANCH (last 14 days)"
SINCE="14 days ago"
RECENT="$(git log "origin/$DEFAULT_BRANCH" --since="$SINCE" --pretty=format:'  %h  %s' --no-merges 2>/dev/null | head -10)"
if [ -n "$RECENT" ]; then
  echo "$RECENT"
else
  note "(none in last 14 days)"
fi

# ---------- 5. Stale branches (local + remote) ----------
heading "Stale branches (no activity in 30+ days)"
STALE_CUTOFF="$(date -v-30d +%s 2>/dev/null || date -d '30 days ago' +%s 2>/dev/null || echo 0)"
STALE_FOUND=0
# Iterate over local + remote branches, skip default and HEAD
git for-each-ref --format='%(refname:short) %(committerdate:unix)' \
  refs/heads refs/remotes/origin 2>/dev/null \
  | while read -r ref ts; do
      case "$ref" in
        "$DEFAULT_BRANCH"|"origin/$DEFAULT_BRANCH"|"origin/HEAD") continue ;;
      esac
      if [ -z "$ts" ] || [ "$ts" -lt "$STALE_CUTOFF" ] 2>/dev/null; then
        if [ -n "$ts" ] && [ "$ts" != "0" ]; then
          AGE_DAYS="$(( ( $(date +%s) - ts ) / 86400 ))"
          printf '  %s  (%s days old)\n' "$ref" "$AGE_DAYS"
          STALE_FOUND=1
        fi
      fi
    done | head -10

# ---------- 6. Recent local commits ----------
heading "Recent commits on $BRANCH (last 5)"
git log -5 --pretty=format:'  %h  %ar  %s' 2>/dev/null || true
echo

exit 0
