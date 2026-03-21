#!/usr/bin/env python3
"""Install the orchestrator PostToolUse hook into Claude Code settings."""

import json
import sys
from pathlib import Path

SETTINGS_FILE = Path.home() / ".claude" / "settings.json"
HOOK_SCRIPT = str(Path(__file__).parent / "post_tool_use.py")


def install():
    if not SETTINGS_FILE.exists():
        settings = {}
    else:
        with open(SETTINGS_FILE) as f:
            settings = json.load(f)

    hooks = settings.setdefault("hooks", {})
    post_tool_use = hooks.setdefault("PostToolUse", [])

    for hook in post_tool_use:
        if "orchestrator" in hook.get("command", ""):
            print("Hook already installed.")
            return

    post_tool_use.append({
        "type": "command",
        "command": f"python3 {HOOK_SCRIPT}",
        "description": "Orchestrator session capture — logs MCP tool calls",
    })

    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

    print(f"Hook installed. Logging to {Path.home() / '.claude' / 'orchestrator' / 'session-log.jsonl'}")


def uninstall():
    if not SETTINGS_FILE.exists():
        print("No settings file found.")
        return

    with open(SETTINGS_FILE) as f:
        settings = json.load(f)

    hooks = settings.get("hooks", {})
    post_tool_use = hooks.get("PostToolUse", [])
    hooks["PostToolUse"] = [h for h in post_tool_use if "orchestrator" not in h.get("command", "")]

    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

    print("Hook uninstalled.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "uninstall":
        uninstall()
    else:
        install()
