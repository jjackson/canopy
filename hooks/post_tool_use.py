#!/usr/bin/env python3
"""Claude Code PostToolUse hook for orchestrator session capture.

Reads hook data from stdin (JSON), detects MCP tool calls,
and appends to ~/.claude/canopy/session-log.jsonl.

Exit 0 always — hook failures should never block Claude Code.
"""

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path.home() / ".claude" / "canopy" / "session-log.jsonl"
REPO_MAP_FILE = Path.home() / ".claude" / "canopy" / "repo-map.json"
_PLUGINS_FILE = Path.home() / ".claude" / "plugins" / "installed_plugins.json"

_seen_sessions: set[str] = set()
_cached_version: str | None = None


def _get_plugin_version() -> str:
    """Return the installed canopy plugin version, cached after first read."""
    global _cached_version
    if _cached_version is not None:
        return _cached_version
    try:
        with open(_PLUGINS_FILE) as f:
            data = json.load(f)
        plugins = data.get("plugins", {})
        for key, value in plugins.items():
            if "canopy" in key:
                entries = value if isinstance(value, list) else [value]
                if entries:
                    version = entries[0].get("version", "unknown")
                    _cached_version = version
                    return _cached_version
    except Exception:
        pass
    _cached_version = "unknown"
    return _cached_version


def maybe_capture_repo(project_dir: str):
    """Capture git remote -> repo mapping if not already known.

    Uses JSON (stdlib) instead of YAML to avoid dependency issues —
    the hook must work with any system Python.
    """
    import subprocess
    import re

    project_key = "-" + project_dir.lstrip("/").replace("/", "-")

    # Check if already mapped
    repo_map = {}
    if REPO_MAP_FILE.exists():
        try:
            with open(REPO_MAP_FILE) as f:
                repo_map = json.load(f)
        except Exception:
            repo_map = {}

    if project_key in repo_map:
        return

    # Try to get git remote
    try:
        result = subprocess.run(
            ["git", "-C", project_dir, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode != 0:
            return
        url = result.stdout.strip()
    except Exception:
        return

    # Extract owner/repo
    match = re.search(r"github\.com[:/]([^/]+/[^/\s]+?)(?:\.git)?$", url)
    if not match:
        return

    repo_map[project_key] = match.group(1)
    REPO_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPO_MAP_FILE, "w") as f:
        json.dump(repo_map, f, indent=2)

try:
    from orchestrator.capture import append_log_entry
except ImportError:
    # Fallback: package not installed; write inline so the hook never breaks.
    def append_log_entry(log_file: Path, entry: dict) -> None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")


def main():
    try:
        hook_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return

    # Always capture repo mapping — runs on every tool call, not just MCP
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if project_dir:
        maybe_capture_repo(project_dir)

    # Emit session_start on first call for this session
    session_id = hook_data.get("session_id", "unknown")
    if session_id not in _seen_sessions:
        _seen_sessions.add(session_id)
        start_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event": "session_start",
            "plugin_version": _get_plugin_version(),
            "project": os.environ.get("CLAUDE_PROJECT_DIR", "unknown"),
        }
        append_log_entry(LOG_FILE, start_entry)

    tool_name = hook_data.get("tool_name", "")

    # Emit skill_invoked for Skill tool calls and return
    if tool_name == "Skill":
        tool_input = hook_data.get("tool_input", {})
        skill_name = tool_input.get("skill", "") if isinstance(tool_input, dict) else ""
        skill_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event": "skill_invoked",
            "skill": skill_name,
            "plugin_version": _get_plugin_version(),
            "project": os.environ.get("CLAUDE_PROJECT_DIR", "unknown"),
        }
        append_log_entry(LOG_FILE, skill_entry)
        return

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

    append_log_entry(LOG_FILE, entry)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
