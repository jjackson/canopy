---
name: select-session
description: Menu-driven session picker — select a project, browse session history, and run the analyzer on a chosen session
version: 0.1.0
---

# Select Session

Interactive menu-driven flow to pick a session and analyze it.

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

Group sessions by their `repo` field (fall back to `project_key` if repo is null).

Present a numbered list of projects with session counts, sorted by most recent activity:

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

### Step 4: Analyze

Run the analyzer on the selected session's `path`:

```bash
uv run canopy analyze <PATH>
```

Show the output to the user.

## Rules

- Always use `uv run` to invoke the orchestrator CLI
- The working directory for commands is `~/emdash-projects/canopy-orchestrator` (or the current worktree)
- If the user types `b` or `back`, go back to the previous menu
- If the user types `q` or `quit`, exit the flow
- Keep the menus clean and minimal — no extra decoration
- Truncate first_msg to 45 characters in the session list
