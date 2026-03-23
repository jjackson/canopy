---
name: select-session
description: Menu-driven session picker — select a project, browse session history, analyze, and propose fixes
version: 0.2.0
---

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

Present using `AskUserQuestion` with projects as options. Include session count and most recent timestamp in each option's description.

Example:
```
AskUserQuestion({
  questions: [{
    question: "Which project do you want to explore?",
    header: "Project",
    options: [
      { label: "canopy-orchestrator", description: "5 sessions, latest: 03-23 15:08" },
      { label: "connect-labs", description: "3 sessions, latest: 03-23 14:25" },
      { label: "commcare-connect", description: "2 sessions, latest: 03-23 12:42" }
    ],
    multiSelect: false
  }]
})
```

Limit to 4 options (the most recently active projects). If the user selects "Other", ask them to type the project name.

### Step 3: Session selection

Show sessions for the chosen project, sorted newest-first.

Present using `AskUserQuestion` with sessions as options. Use the truncated first message as the label and message count + date as the description.

Example:
```
AskUserQuestion({
  questions: [{
    question: "Which session?",
    header: "Session",
    options: [
      { label: "I would like a way to quickly nav...", description: "4 msgs · 03-23 15:08" },
      { label: "I think we are ready to test, is...", description: "88 msgs · 03-23 14:25" }
    ],
    multiSelect: false
  }]
})
```

Truncate first_msg to 35 characters in the label. Limit to 4 options (most recent). If the user selects "Other", show the full list as text and ask them to pick by number.

### Step 4: Analyze and propose

Run the analyzer with `--propose` to get both observations and implementation suggestions:

```bash
uv run canopy analyze --propose <PATH>
```

**Show the full output directly to the user** — do not summarize or hide it in a tool call. Present each observation with its severity, then each proposal with its implementation plan.

### Step 5: Disposition

After showing the analysis and proposals, present each proposal using `AskUserQuestion` so the user can decide what to do:

```
AskUserQuestion({
  questions: [
    {
      question: "Proposal: <title>\n\n<what/why/how summary>\n\nWhat would you like to do?",
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

### Step 6: Implement

For any proposals the user marked "Implement":

1. Identify the target repo from the session data
2. Tell the user what will be implemented and in which repo
3. Use `uv run canopy analyze` output as the implementation spec
4. Create a branch, implement the fix, and verify

If no proposals were marked for implementation, summarize what was backlogged/skipped and end.

## Rules

- Always use `uv run` to invoke the orchestrator CLI
- Use `AskUserQuestion` for all menu selections — do not present plain text menus
- Show analysis and proposal output directly to the user, not hidden in tool results
- The full flow is: select → analyze → propose → disposition → implement
- If the user selects "Other" on any menu, handle gracefully
- Keep labels short and descriptions informative
