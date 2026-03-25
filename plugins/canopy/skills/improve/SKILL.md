---
name: improve
description: Run a full canopy improvement cycle — analyze recent sessions, propose improvements, and optionally implement them
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
[ -n "$_CANOPY_UPD" ] && echo "$_CANOPY_UPD"
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# Improve

Runs the canopy improvement pipeline on recent Claude Code sessions.

## Arguments

- No args: full cycle (analyze + propose + implement)
- `observe`: analyze only, no proposals
- `dry-run`: analyze + propose, no implementation

## Flow

1. Run the appropriate command from the canopy repo working directory:

```bash
# Full cycle
uv run canopy improve

# Observe only
uv run canopy improve --observe-only

# Dry run
uv run canopy improve --dry-run
```

2. Show progress as it runs (the command streams output)
3. Display the results summary: transcripts analyzed, observations created, proposals generated, implementations completed

## Rules

- Always use `uv run` to invoke the canopy CLI
- The working directory is the canopy repo (wherever `pyproject.toml` with `name = "canopy"` is)
- The command may take several minutes — it invokes `claude -p` for analysis and proposal generation
- If the circuit breaker trips (too many consecutive failures), the command will report this
