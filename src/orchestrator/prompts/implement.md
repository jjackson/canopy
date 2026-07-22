You are implementing an improvement to an MCP tool ecosystem. A proposal has
been generated from real usage analysis, and you need to execute it.

## Proposal

{proposal_yaml}

## Why This Is Needed

{observation_yaml}

## Instructions

Implement the proposed change in this repository. Specifically:

1. Create a feature branch: `git checkout -b orchestrator/<short-description>`
2. Read the existing code to understand the current structure
3. Implement the change described in the proposal
4. Write tests for the new functionality
5. Run the tests and make sure they pass
6. Commit with a descriptive message
7. If tests pass, merge to main: `git checkout main && git merge orchestrator/<short-description>`
8. If tests fail, leave the branch unmerged and exit with a non-zero status

If this is a new MCP tool, follow the existing patterns in this repo for how
tools are defined and registered.

If the implementation is not feasible (missing dependencies, would break existing
functionality, or the proposal is unclear), explain why and exit without making
changes.
