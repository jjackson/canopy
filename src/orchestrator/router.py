"""Tiered routing — classify proposals by complexity and route to cheapest tier.

Inspired by Citadel's four-tier model, simplified to three:
- inline: simple fix, no subprocess (config change)
- single: one claude -p session (new tool, improvement)
- team: agent team with parallel teammates (new server, complex refactor)
"""

# Default budgets and timeouts per tier
TIER_CONFIG = {
    "inline": {"budget": 0, "timeout": 0, "description": "No subprocess needed"},
    "single": {"budget": 2.00, "timeout": 600, "description": "One claude -p session"},
    "team": {"budget": 10.00, "timeout": 1800, "description": "Agent team with teammates"},
}

# Proposal type → default tier
TYPE_TIER_MAP = {
    "new_tool": "single",
    "tool_improvement": "single",
    "new_skill": "single",
    "hook_improvement": "single",
    "new_workflow": "single",
    "new_server": "team",
}


def classify_proposal(proposal: dict) -> str:
    """Classify a proposal into a tier: inline, single, or team."""
    ptype = proposal.get("type", "")
    complexity = proposal.get("complexity", "medium")

    # Complexity override
    if complexity == "low" and ptype != "new_server":
        return "single"
    if complexity == "high":
        return "team"

    # Default by type
    return TYPE_TIER_MAP.get(ptype, "single")


def route_proposal(proposal: dict, config: dict | None = None) -> dict:
    """Return execution plan for a proposal with tier, budget, timeout."""
    tier = classify_proposal(proposal)
    tier_config = (config or {}).get(tier, TIER_CONFIG.get(tier, TIER_CONFIG["single"]))

    return {
        "tier": tier,
        "budget": tier_config.get("budget", TIER_CONFIG[tier]["budget"]),
        "timeout": tier_config.get("timeout", TIER_CONFIG[tier]["timeout"]),
        "description": tier_config.get("description", TIER_CONFIG[tier]["description"]),
    }
