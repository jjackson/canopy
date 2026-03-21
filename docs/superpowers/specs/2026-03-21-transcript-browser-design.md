# Transcript Browser — Design Document

**Date:** 2026-03-21
**Status:** Draft

## Problem

The orchestrator can analyze transcripts and generate proposals, but there's no
way to browse, triage, and label sessions. Picking which transcript to analyze
requires manually listing files and guessing from paths. There's also no way to
attach metadata (quality labels, use-case tags, notes) that would help the
orchestrator prioritize what to improve.

## Solution

A lightweight localhost web UI (`orchestrator serve`) for browsing, labeling,
and triggering analysis on Claude Code session transcripts. Python's built-in
HTTP server, no new dependencies.

The browser serves three purposes:
1. **Browse & triage** — see all transcripts grouped by GitHub repo with useful
   metadata, quickly identify interesting sessions
2. **Label for evaluation** — mark sessions with quality ratings, use-case tags,
   and notes to guide the improvement pipeline
3. **Analyze & propose** — trigger transcript analysis and proposal generation
   directly from the UI

**Future (not in scope for v1):** launching parallel implementations from the
browser, deeper emdash integration, transcript cleanup/archival.

## Architecture

Single Python module (`src/orchestrator/server.py`) that:
- Serves a single-page app (vanilla HTML/JS) from a bundled template
- Exposes JSON API endpoints for transcript data, labels, and actions
- Runs on localhost only

```
Browser (localhost:8484)
  ├── GET /                     → serves the SPA
  ├── GET /api/transcripts      → list all transcripts with metadata + labels
  ├── GET /api/transcript/:id   → full transcript content
  ├── POST /api/labels/:id      → save labels for a transcript
  ├── POST /api/analyze/:id     → trigger analysis, save observations to disk
  ├── POST /api/propose/:id     → generate proposals from saved observations
  └── POST /api/review/:id      → trigger AI strategic review
```

**Transcript ID:** The `:id` in all endpoints is the JSONL filename stem (the
session UUID without `.jsonl`). This is always present and stable, unlike the
session ID from `last-prompt` which may be absent in some files.

### Transcript Discovery

Scans `~/.claude/projects/*/` for JSONL files. For each transcript, extracts:
- Session ID (from `last-prompt` entry or filename)
- Timestamps (first and last entry)
- Line count
- User message count and first user message (preview)
- MCP tool calls (names and counts)
- GitHub repo (from metadata — see Repo Mapping below)

### Repo Mapping

**Problem:** Emdash creates worktrees with random names that get cleaned up,
so `git remote get-url origin` often fails for old transcripts.

**Solution:** A mapping file at `~/.claude/orchestrator/repo-map.yaml` that
maps project directory names to GitHub repos:

```yaml
# Auto-populated by the hook for new sessions
-Users-jjackson-emdash-projects-worktrees-project-test-6kt: jjackson/chrome-sales
-Users-jjackson-emdash-projects-connect-labs: jjackson/connect-labs

# Manually assigned via the UI for old sessions
-Users-jjackson-emdash-projects-worktrees-free-spies-jump-5g0: jjackson/chrome-sales
```

The PostToolUse hook is updated to capture `git remote get-url origin` on
first call per session and write to `repo-map.yaml`. For existing transcripts,
the UI provides a way to manually assign repos.

**Hook implementation:** Before logging the MCP call, the hook checks if the
current project directory key already exists in `repo-map.yaml`. If not, it
runs `git -C <project_dir> remote get-url origin`, extracts `owner/repo` from
the URL, and writes the mapping. If the git command fails (non-git directory,
no remote), it silently skips. The project directory comes from
`CLAUDE_PROJECT_DIR` env var (already captured by the hook).

### Labels Storage

Labels are stored in `~/.claude/orchestrator/labels.yaml`:

```yaml
cfaf8c29-7785-4190-aef7-756b25390f34:
  quality: had-friction
  use_case_tags: [funder-research, salesforce, google-drive]
  eval_candidate: true
  notes: "Good test case for Drive permission improvements"

96b3e009-5cfc-4bb3-9284-b3b5e5472201:
  quality: skip-coding
  use_case_tags: [local-dev-setup]
  eval_candidate: false
  notes: ""
```

Quality values: `unlabeled`, `went-well`, `had-friction`, `disaster`,
`skip-coding`, `skip-setup`, `good-for-eval`.

## UI Design

### Main View — Transcript List

Transcripts grouped by GitHub repo, collapsible, sessions ordered newest-first
within each repo.

**Repo header row:**
- Repo name (e.g., `jjackson/chrome-sales`)
- Session count
- MCP tools used across all sessions in that repo

**Session row:**
- Date
- First user message (preview, truncated)
- Line count, user message count
- MCP call count (if any)
- Status badges: `analyzed`, `active`, label

**Unmapped sessions** appear in a separate bucket with an "Assign repo" action.

**Filter bar:** Has MCP | Labeled | Unlabeled | By repo

### Detail View — Expanded Session

Clicking a session row expands to show:

**Stats bar:** MCP calls, user messages, errors, observation count

**Tool usage:** which MCP tools were called and how many times

**Observations:** if already analyzed, show the observation list with severity

**Actions:**
- **Analyze** — runs `analyze_transcript()`, saves observations to
  `~/.claude/orchestrator/observations/` via `save_observation()`, displays
  results inline. Proposals can then be generated from these saved observations.
- **AI Review** — strategic review applying Gstack-style thinking (see below).
  Results saved to `~/.claude/orchestrator/ai-reviews/<session_id>.yaml`.
- **Full Transcript** — expand to show the complete conversation as a chat log
- **Label controls** — quality dropdown, use-case tag input, notes textarea

**Propose** (`POST /api/propose/:id`): reads observations from
`~/.claude/orchestrator/observations/` that were created by a prior Analyze
action for this session, then calls `generate_proposals()`. Results saved to
`~/.claude/orchestrator/proposals/` via `save_proposal()`. This reuses the
existing pipeline data stores — observations and proposals persist across
server restarts.

**Full transcript view:** renders the conversation chronologically as
USER / ASSISTANT / TOOL_CALL / TOOL_RESULT blocks. Collapsible thinking
blocks. Tool results truncated with "show more."

### AI Review

Beyond mechanical observation extraction, the browser offers a strategic review
mode inspired by Gstack's review patterns. When triggered, it invokes
`claude -p` with the same chronological transcript rendering used by
`build_analysis_prompt()` (USER/ASSISTANT/TOOL_CALL/TOOL_RESULT summary),
but with a different prompt that applies product-thinking:

- What was the user really trying to accomplish?
- What's the highest-leverage improvement that would help?
- Are there entirely new tools or approaches that weren't considered?
- What recurring patterns could be automated as workflows?
- If you could only build one thing from this session, what would it be?

Results are saved to `~/.claude/orchestrator/ai-reviews/<session_id>.yaml`
as free-form markdown (not structured observations). Displayed in the detail
view under an "AI Review" section. Same 120-second timeout as analysis.

## CLI Integration

```bash
orchestrator serve                  # start on port 8484
orchestrator serve --port 9090      # custom port
```

The server runs in the foreground and logs requests. Ctrl+C to stop.

## What's NOT in v1

- Transcript cleanup/archival/deletion
- Launching implementations from the browser
- Emdash integration
- Real-time updates (page refresh to see new data)
- Authentication (localhost only, single user)
- Persistent background server (must be started manually)

## Key Design Decisions

- **Zero new dependencies** — uses Python's `http.server` and vanilla JS.
  Keeps the orchestrator's "stay simple" philosophy.
- **Labels stored separately from transcripts** — never modify Claude's
  transcript files. Labels live in the orchestrator's own state directory.
- **Repo mapping is best-effort** — auto-populated going forward via the hook,
  manually assignable for old sessions. Unmapped sessions are still usable.
- **Analysis runs synchronously** — when you click "Analyze," the browser
  waits for `claude -p` to finish and shows results inline. This is fine for
  a single-user localhost tool.
- **AI Review is a separate action from Analyze** — Analyze extracts
  observations mechanically. AI Review applies strategic/creative thinking.
  Different prompts, different purposes, can be run independently.
