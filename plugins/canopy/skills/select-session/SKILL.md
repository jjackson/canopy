---
name: select-session
description: Menu-driven session picker — select a project, browse session history, analyze, and propose fixes
version: 0.3.0
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
[ -n "$_CANOPY_UPD" ] && echo "$_CANOPY_UPD"
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# Select Session

Interactive menu-driven flow to pick a session, analyze it, and propose improvements.

## Arguments

- `hours` (optional): Time window for recent sessions. Default: 24. Example: `/select-session 72`

## Flow

### Step 1: Fetch session data

Run this command, substituting the hours argument (default 24):

```bash
uv run canopy sessions list --json-output --hours <HOURS>
```

Parse the JSON output. If no sessions found, tell the user and suggest increasing the hours window.

### Step 2: Project selection

Group sessions by their `repo` field (fall back to `project_key` if repo is null). Sort by most recent activity.

Present a numbered text menu:

```
Select a project:

  1  jjackson/canopy-orchestrator    (5 sessions)
  2  jjackson/connect-labs           (3 sessions)
  3  dimagi/commcare-connect         (2 sessions)
  4  jjackson/connect-search         (2 sessions)
```

Wait for the user to pick a number.

### Step 3: Session selection

Show sessions for the chosen project, sorted newest-first:

```
jjackson/canopy-orchestrator — recent sessions:

  1  [03-23 15:08]  "I would like a way to quickly navigate..."   (4 msgs)
  2  [03-23 14:25]  "I think we are ready to test, is that..."    (88 msgs)
  3  [03-23 14:17]  "What are my most recent connect-search..."   (2 msgs)
```

Wait for the user to pick a number.

### Step 4: Analyze and propose

Run the analyzer with `--propose` to get both observations and implementation suggestions:

```bash
uv run canopy analyze --propose <PATH>
```

**Show the full output directly to the user** — do not summarize or hide it in a tool call. Present each observation with its severity, then each proposal with its implementation plan.

### Step 5: Disposition

After showing the analysis and proposals, present each proposal using `AskUserQuestion` so the user can decide what to do. Bundle up to 4 proposals into a single `AskUserQuestion` call (one question per proposal):

```
AskUserQuestion({
  questions: [
    {
      question: "Proposal: <title>\n\n<what/why/how summary>",
      header: "<short label>",
      options: [
        { label: "Implement", description: "Fix this now" },
        { label: "Backlog", description: "Good idea, not now" },
        { label: "Skip", description: "Not worth doing" }
      ],
      multiSelect: false
    }
    // ... one per proposal, up to 4
  ]
})
```

If there are more than 4 proposals, batch them into multiple `AskUserQuestion` calls.

### Step 6: Implement

For any proposals the user marked "Implement":

1. Identify the target repo from the session data
2. Tell the user what will be implemented and in which repo
3. Use `uv run canopy analyze` output as the implementation spec
4. Create a branch, implement the fix, and verify

If no proposals were marked for implementation, summarize what was backlogged/skipped and end.

## Rules

- Always use `uv run` to invoke the orchestrator CLI
- Use plain text numbered menus for project and session selection (no item limit)
- Use `AskUserQuestion` only for proposal disposition (fixed 3 options per proposal)
- Show analysis and proposal output directly to the user, not hidden in tool results
- The full flow is: select → analyze → propose → disposition → implement
- If the user types `b` or `back`, go back to the previous menu
- If the user types `q` or `quit`, exit the flow
- Truncate first_msg to 45 characters in the session list
- Keep the menus clean and minimal — no extra decoration
