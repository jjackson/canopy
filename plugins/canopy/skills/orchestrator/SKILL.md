---
name: orchestrator
description: Cross-project MCP orchestration — routes queries to the right tools across multiple projects
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
[ -n "$_CANOPY_UPD" ] && echo "$_CANOPY_UPD"
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# Cross-Project Orchestrator

You have access to MCP tools across multiple projects. This skill tells you which tools exist, what they do, and how to compose them for cross-project workflows.

## How to Use This

When the user asks a question that might require tools from multiple MCP servers:

1. Check the Capability Registry below to identify which servers and tools are relevant
2. Check the Workflows section to see if there's a known workflow for this type of request
3. If a workflow exists, follow its steps in order
4. If no workflow exists, use the registry's `answers` patterns to identify the right servers

## Important

- Always start with the most upstream server (e.g., connect-search for context, then commcare-hq for app structure, then scout-data for analytics)
- When a workflow step is marked `optional`, skip it if the user's request doesn't need that data
- For write operations (data_access: read-write), confirm with the user before executing
- Log your routing decisions — which servers you chose and why — so the learning engine can improve future routing

## Capability Registry

Read the registry file to understand available MCP servers and workflows:

**Registry location:** `~/emdash-projects/canopy-orchestrator/registry.yaml`

Read this file at the start of any session where cross-project orchestration may be needed.
The registry contains:
- All available MCP servers grouped by domain
- What questions each server can answer (the `answers` field)
- What tools each server exposes
- Known multi-server workflows with step-by-step sequences
