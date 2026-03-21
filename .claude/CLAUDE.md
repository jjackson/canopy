# Canopy Orchestrator

Self-improving MCP orchestration system. Composes MCP servers across projects,
learns from usage patterns, and auto-evolves tools via autoresearch.

## Tech Stack
- Python 3.11+, PyYAML, Click
- Claude Code hooks and skills

## Key Files
- `registry.yaml` — capability registry mapping MCP servers to their tools
- `src/orchestrator/registry.py` — registry loader and validator
- `src/orchestrator/capture.py` — session log writer (PostToolUse hook logic)
- `hooks/post_tool_use.py` — Claude Code hook for session capture
- `skills/orchestrator/SKILL.md` — Claude Code skill for cross-project routing

## Commands
- `orchestrator registry show` — display loaded registry
- `orchestrator registry validate` — check registry against live MCP servers
- `orchestrator corpus add <session-id>` — add a session to the activity corpus

## Testing
- `pytest` from project root
