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
- `orchestrator registry show [--format summary|skill|json]` — display loaded registry
- `orchestrator registry validate` — validate registry.yaml structure
- `orchestrator sessions status` — show session log entry count and classification summary

## Testing
- `pytest` from project root
