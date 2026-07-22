You are analyzing a Claude Code session transcript to identify improvements for
an MCP tool ecosystem. Your job is to find friction, gaps, patterns, and missing
capabilities.

## Transcript

{transcript_text}

## Instructions

Analyze this transcript and output a YAML list of observations. Each observation
should have:

- `type`: one of `friction`, `gap`, `pattern`, `missing_capability`
- `description`: what you observed (1-2 sentences)
- `severity`: `low`, `medium`, or `high`
- `related_servers`: list of MCP server names involved (can be empty)
- `lifecycle_stage`: which part of the workflow this relates to (e.g.,
  "research", "solicitation-creation", "training-material-creation", or null)
- `evidence`: brief quote or summary from the transcript showing this

**Definitions:**
- `friction`: a tool was used but worked poorly (failed, retried, unhelpful
  results)
- `gap`: the user did something manually that could have been automated with a
  tool
- `pattern`: a multi-tool sequence that recurs and could become a workflow
- `missing_capability`: the user needed something that no server, skill, or hook
  could handle

Only include real observations. If the session went smoothly with no issues,
output an empty list: `[]`

Output ONLY valid YAML. No commentary before or after.
