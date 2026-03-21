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
- `verification`: a dict describing how to prove this improvement works:
  - `type`: one of:
    - `replay` — re-run the exact tool call that failed; after the fix it should
      succeed or return a better error
    - `tool_exists` — verify the new tool exists and responds to a sample call
      without error
    - `integration_test` — write a test that exercises the new behavior with
      realistic inputs
    - `observational` — can only be verified by watching future sessions for
      the same friction (lowest confidence)
  - `test_description`: one sentence describing what to test
  - `sample_inputs`: if applicable, the inputs from the observation that can be
    replayed (e.g., the tool call arguments that failed)
  - `expected_outcome`: what success looks like
  - `confidence`: `high`, `medium`, or `low` — how certain are we that this
    test proves the improvement works?

Guidelines:
- Prefer adding to existing servers over creating new ones
- Only propose `new_server` if no existing server is a natural fit
- Be specific: "Add filter_by_status parameter to search_opportunities" not
  "improve search"
- One proposal per observation unless they're clearly the same change
- **Strongly prefer proposals with high verification confidence.** If an
  observation contains a concrete failure (error message, specific inputs),
  the proposal should include a replay-based verification. If the improvement
  can only be verified observationally, say so — these will be deprioritized.

Output ONLY valid YAML. No commentary before or after.
