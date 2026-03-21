"""Load, validate, and query the capability registry."""

from pathlib import Path
from typing import Any

import yaml


class RegistryError(Exception):
    """Raised when the registry is invalid or cannot be loaded."""


def load_registry(path: Path) -> dict[str, Any]:
    """Load and validate a registry YAML file."""
    if not path.exists():
        raise RegistryError(f"Registry file not found: {path}")
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise RegistryError(f"Failed to parse registry YAML: {e}")
    if not isinstance(data, dict) or "version" not in data:
        raise RegistryError("Registry must contain a 'version' field")
    return data


def get_all_servers(registry: dict) -> list[dict]:
    servers = []
    for domain_name, domain in registry.get("domains", {}).items():
        for server_name, server in domain.get("servers", {}).items():
            servers.append({"name": server_name, "domain": domain_name, **server})
    return servers


def get_server(registry: dict, name: str) -> dict | None:
    for server in get_all_servers(registry):
        if server["name"] == name:
            return server
    return None


def get_all_tools(registry: dict) -> list[dict]:
    tools = []
    for server in get_all_servers(registry):
        for tool in server.get("tools", []):
            tools.append({**tool, "server": server["name"], "domain": server["domain"]})
    return tools


def get_workflows(registry: dict) -> dict:
    return registry.get("workflows", {})


def format_for_skill(registry: dict) -> str:
    """Render registry as markdown for Claude Code skill context."""
    lines = ["# Capability Registry", ""]
    for domain_name, domain in registry.get("domains", {}).items():
        lines.append(f"## Domain: {domain_name}")
        lines.append(f"{domain.get('description', '')}")
        lines.append("")
        for server_name, server in domain.get("servers", {}).items():
            lines.append(f"### Server: {server_name}")
            lines.append(f"**Description:** {server.get('description', '')}")
            lines.append(f"**Data access:** {server.get('data_access', 'unknown')}")
            lines.append("")
            answers = server.get("answers", [])
            if answers:
                lines.append("**Questions this server can answer:**")
                for a in answers:
                    lines.append(f"- {a}")
                lines.append("")
            tools = server.get("tools", [])
            if tools:
                lines.append("**Tools:**")
                for t in tools:
                    lines.append(f"- `{t['name']}` — {t.get('description', '')}")
                    if t.get("typical_use"):
                        lines.append(f"  - Typical use: {t['typical_use']}")
                lines.append("")
    workflows = registry.get("workflows", {})
    if workflows:
        lines.append("## Workflows")
        lines.append("")
        for wf_name, wf in workflows.items():
            lines.append(f"### Workflow: {wf_name}")
            lines.append(f"**Description:** {wf.get('description', '')}")
            triggers = wf.get("trigger_phrases", [])
            if triggers:
                lines.append(f"**Triggers:** {', '.join(triggers)}")
            lines.append("**Steps:**")
            for i, step in enumerate(wf.get("steps", []), 1):
                optional = " (optional)" if step.get("optional") else ""
                lines.append(f"{i}. **{step['server']}**: {step['action']}{optional}")
                lines.append(f"   - Purpose: {step['purpose']}")
            lines.append("")
    return "\n".join(lines)
