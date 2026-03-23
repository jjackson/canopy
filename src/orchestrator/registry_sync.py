"""Auto-sync registry with actual MCP tools from repos.

Scans each server's repo for @mcp.tool decorators and updates
the registry to reflect what actually exists. This is step 0 of
every improvement cycle — the pipeline must know what tools exist
before it can identify what's missing.
"""
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml


def scan_mcp_tools(repo_path: Path, mcp_path: str) -> list[dict]:
    """Scan a repo's MCP server files for @mcp.tool decorated functions.

    Returns list of dicts with 'name' key for each tool found.
    """
    full_path = repo_path / mcp_path
    if not full_path.exists():
        return []

    tools = []
    py_files = list(full_path.glob("**/*.py"))

    for py_file in py_files:
        # Skip venvs, caches, tests
        parts = py_file.parts
        if any(p in parts for p in [".venv", "__pycache__", "node_modules"]):
            continue

        try:
            content = py_file.read_text()
        except (OSError, UnicodeDecodeError):
            continue

        # Find @mcp.tool() or @server.tool() or @app.tool() decorated functions
        # Pattern: decorator line followed by async def or def
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"@(mcp|server|app)\.tool\b", stripped):
                # Look for the function definition in the next few lines
                for j in range(i + 1, min(i + 5, len(lines))):
                    func_match = re.match(r"\s*(?:async\s+)?def\s+(\w+)\s*\(", lines[j])
                    if func_match:
                        tools.append({"name": func_match.group(1)})
                        break

    return tools


def sync_registry(registry_path: Path) -> dict:
    """Sync registry tools with what actually exists in repos.

    Returns a summary: {server_name: {added: [...], removed: [...], unchanged: int}}
    """
    with open(registry_path) as f:
        registry = yaml.safe_load(f)

    summary = {}

    for domain_name, domain in registry.get("domains", {}).items():
        for server_name, server in domain.get("servers", {}).items():
            repo = server.get("repo", "")
            mcp_path = server.get("mcp_path", "")

            if not repo or not mcp_path:
                continue

            repo_path = Path(repo).expanduser()
            if not repo_path.exists():
                summary[server_name] = {"error": f"Repo not found: {repo_path}"}
                continue

            # Scan actual tools
            actual_tools = scan_mcp_tools(repo_path, mcp_path)
            actual_names = {t["name"] for t in actual_tools}

            # Current registry tools
            current_tools = server.get("tools", [])
            current_names = {t["name"] for t in current_tools}

            added = actual_names - current_names
            removed = current_names - actual_names
            unchanged = len(actual_names & current_names)

            if added or removed:
                # Rebuild tool list: keep existing entries for unchanged tools,
                # add new entries for discovered tools, drop removed ones
                new_tools = []
                for tool in current_tools:
                    if tool["name"] in actual_names:
                        new_tools.append(tool)

                for name in sorted(added):
                    new_tools.append({
                        "name": name,
                        "description": f"(auto-discovered — needs description)",
                        "typical_use": "",
                    })

                server["tools"] = new_tools

            summary[server_name] = {
                "added": sorted(added),
                "removed": sorted(removed),
                "unchanged": unchanged,
                "total": len(actual_names),
            }

    # Write back
    registry["updated"] = __import__("datetime").date.today().isoformat()
    with open(registry_path, "w") as f:
        yaml.dump(registry, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True, width=120)

    return summary
