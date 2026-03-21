You are generating improvement proposals for an MCP tool ecosystem. Based on
observations from real usage sessions, propose concrete changes.

## Current Ecosystem

{registry_summary}

## Observations to Address

{observations_yaml}

## Instructions

For each observation (or group of related observations), generate a proposal.
Output a YAML list where each proposal has:

- `type`: one of `new_tool`, `new_server`, `tool_improvement`, `new_skill`,
  `new_workflow`, `hook_improvement`, `registry_update`
- `action`: what to do (be specific — name the tool, describe the feature)
- `target_repo`: the repo path to modify (from the registry, e.g.,
  `~/emdash-projects/connect-labs`)
- `ownership`: `self`, `team`, or `external` (from the registry)
- `motivation`: why this is needed (reference the observation)
- `observation_id`: the ID of the observation this addresses
- `complexity`: `low`, `medium`, or `high`

Guidelines:
- Prefer adding to existing servers over creating new ones
- Only propose `new_server` if no existing server is a natural fit
- Be specific: "Add filter_by_status parameter to search_opportunities" not
  "improve search"
- One proposal per observation unless they're clearly the same change

Output ONLY valid YAML. No commentary before or after.
