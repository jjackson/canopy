---
name: patterns
description: Show cross-session friction patterns — recurring issues and project hotspots detected across Claude Code sessions
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash "$HOME/emdash-projects/canopy/plugins/canopy/scripts/canopy-update-check.sh" 2>/dev/null || bash "$HOME/.claude/plugins/marketplaces/canopy/plugins/canopy/scripts/canopy-update-check.sh" 2>/dev/null || true)
case "$_CANOPY_UPD" in UPGRADE_AVAILABLE*) echo "$_CANOPY_UPD" ;; esac
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# Patterns

Shows aggregated patterns from session analysis — recurring issues ranked by frequency and project hotspots by issue count.

## Flow

1. Run from the canopy repo working directory:

```bash
uv run canopy patterns
```

2. Display the output showing:
   - Recurring issues: grouped by type and related servers, ranked by total frequency
   - Project hotspots: servers with the most issues, flagging high-severity concentrations

## Options

- `--json-output`: Output as JSON for programmatic consumption

## Rules

- This reads from `~/.claude/canopy/observations/` — requires running `canopy improve` at least once first
- If no patterns are detected, suggest running `canopy improve` to populate observations
