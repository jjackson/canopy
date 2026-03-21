#!/usr/bin/env python3
"""Claude Code PostToolUse hook for orchestrator session capture.

Reads hook data from stdin (JSON), detects MCP tool calls,
and appends to ~/.claude/orchestrator/session-log.jsonl.

Exit 0 always — hook failures should never block Claude Code.
"""

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path.home() / ".claude" / "orchestrator" / "session-log.jsonl"


def main():
    try:
        hook_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return

    tool_name = hook_data.get("tool_name", "")
    if not tool_name.startswith("mcp__"):
        return

    parts = tool_name.split("__", 2)
    if len(parts) < 3:
        return

    server_name = parts[1]
    mcp_tool = parts[2]

    tool_input = hook_data.get("tool_input", {})
    input_summary = {}
    if isinstance(tool_input, dict):
        for k, v in tool_input.items():
            if isinstance(v, str) and len(v) > 100:
                input_summary[k] = v[:100] + "..."
            else:
                input_summary[k] = v

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": hook_data.get("session_id", "unknown"),
        "project": os.environ.get("CLAUDE_PROJECT_DIR", "unknown"),
        "server": server_name,
        "tool": mcp_tool,
        "input_summary": input_summary,
        "success": not hook_data.get("tool_error"),
    }

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
