---
description: Show PM skill status for the current project — last run, lens rotation, backlog, recent learnings
allowed-tools: [Read, Glob, Bash]
---

# PM Status

Show a quick overview of PM skill state for the current project.

## Process

1. Check if `.claude/pm/context.md` exists. If not, say "PM not bootstrapped for this project. Run `/pm-scout` to get started."

2. Read `.claude/pm/context.md` and show the project name and "What Matters Most" section.

3. List files in `.claude/pm/runs/` sorted by date. Show:
   - **Last run**: date and lens (from filename)
   - **Next lens**: the next in rotation (user-value → adoption-blockers → integration-depth → trust-reliability → tech-debt → user-value)
   - **Total runs**: count of run files

4. Read `.claude/pm/learnings.md` and show:
   - **Closed items**: count and last 3 titles
   - **Preferences**: count

5. Scan the most recent 3 run logs for any items with status "Backlog". Show:
   - **Backlogged items**: title + which run they came from

Format as a compact status card, not a wall of text.
