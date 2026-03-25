# Canopy

Autonomous self-improving system and Claude Code plugin that watches Claude
Code sessions across all projects, identifies friction and gaps, and builds
improvements — to MCP servers, skills, hooks, workflows, CLAUDE.md docs, or
the orchestrator itself.

Converges with gstack and superpowers: invokes their skills headlessly via the
skill runner for review, QA, and implementation quality.

## Git Worktree Rules
This repo uses emdash which manages git worktrees. If you are in a worktree
(check: `git rev-parse --git-dir` contains `/worktrees/`), then `main` is
checked out in the main repo at `~/emdash-projects/canopy-orchestrator/`.
You CANNOT `git checkout main` from a worktree — it will fail.

To merge to main:
```bash
cd ~/emdash-projects/canopy-orchestrator && git merge <branch-name> && git push
```

If that fails with local changes, stash first:
```bash
cd ~/emdash-projects/canopy-orchestrator && git stash && git merge <branch-name> && git push
```

If remote is ahead, pull first:
```bash
cd ~/emdash-projects/canopy-orchestrator && git pull --rebase && git push
```

## Tech Stack
- Python 3.11+, PyYAML, Click
- Claude Code hooks and skills
- Subprocess invocation of `claude -p` for analysis, proposals, and implementation

## Commands
- `canopy registry show [--format summary|skill|json]` — display loaded registry
- `canopy registry sync` — scan repos for actual MCP tools and update registry
- `canopy registry validate` — validate registry.yaml structure
- `canopy sessions status` — show session log entry count and classification summary
- `canopy sessions list [--hours N] [--json-output]` — list recent sessions
- `canopy improve` — run a full improvement cycle (analyze → propose → implement)
- `canopy improve --observe-only` — analyze transcripts without proposing
- `canopy improve --dry-run` — analyze and propose without implementing
- `canopy serve` — start transcript browser web UI on localhost:8484
- `canopy analyze <transcript.jsonl> [--propose]` — analyze a specific transcript
- `canopy brief [--model MODEL]` — generate strategic brief
- `canopy patterns [--json-output]` — show cross-session friction patterns

## Key Modules

### Core pipeline
- `src/orchestrator/pipeline.py` — full improvement cycle (scanner discovery, circuit breaker, rate limiter)
- `src/orchestrator/analyzer.py` — transcript analysis via claude -p
- `src/orchestrator/proposer.py` — proposal generation via claude -p
- `src/orchestrator/implementer.py` — implementation via claude -p in target repos
- `src/orchestrator/skill_runner.py` — headless invocation of any Claude Code skill

### Data models
- `src/orchestrator/observations.py` — friction, gaps, patterns extracted from sessions
- `src/orchestrator/proposals.py` — improvement proposals with verification plans
- `src/orchestrator/campaigns.py` — multi-day improvement arcs
- `src/orchestrator/tracker.py` — proposal outcome tracking for self-improvement

### Intelligence
- `src/orchestrator/patterns.py` — cross-session pattern detection
- `src/orchestrator/briefing.py` — strategic brief with gstack cognitive patterns
- `src/orchestrator/router.py` — tiered routing (inline/single/team)

### Registry & discovery
- `registry.yaml` — capability registry mapping servers to tools (auto-synced)
- `src/orchestrator/registry.py` — registry loader and validator
- `src/orchestrator/registry_sync.py` — scans @mcp.tool decorators from repos to keep registry accurate
- `src/orchestrator/scanner.py` — transcript discovery and metadata extraction
- `src/orchestrator/transcripts.py` — Claude Code transcript parsing
- `src/orchestrator/repo_map.py` — project-to-GitHub-repo mapping (JSON, stdlib only)

### Capture & hooks
- `hooks/post_tool_use.py` — captures repo mapping on every tool call, logs MCP calls
- `src/orchestrator/capture.py` — session log writer

### Browser UI (visibility tool, not primary interface)
- `src/orchestrator/server.py` — HTTP server with JSON API
- `src/orchestrator/static/index.html` — SPA frontend
- `src/orchestrator/labels.py` — transcript label storage
- `src/orchestrator/reviewer.py` — AI strategic review via claude -p

### Scheduling
- `src/orchestrator/scheduler.py` — launchd plist generation
- `src/orchestrator/circuit_breaker.py` — stops pipeline after consecutive failures
- `src/orchestrator/rate_limiter.py` — caps API calls per hour

### Plugin (Claude Code skills, commands, agents)
- `plugins/canopy/skills/` — skill definitions (select-session, improve, brief, patterns, orchestrator, product-management, doc-regeneration)
- `plugins/canopy/commands/` — slash commands (pm-scout, pm-status, doc-regen, improve, brief, patterns)
- `plugins/canopy/agents/` — autonomous agents (pm-supervisor)
- `.claude-plugin/marketplace.json` — plugin marketplace manifest

## Important: Hook Must Use Stdlib Only
`hooks/post_tool_use.py` runs with system python3 which may not have PyYAML.
The repo map uses JSON (not YAML). Any hook code must use only stdlib modules.

## Plugin Updates — NEVER locally patch

**CRITICAL: Never directly copy, rsync, or write files into `~/.claude/plugins/cache/`
or edit `~/.claude/plugins/installed_plugins.json` by hand.** This is "local patching"
and it bypasses the plugin system, creates version mismatches, and makes bugs hard to
diagnose. If you feel the urge to locally patch, STOP — use `/canopy:update` instead.

### Update workflow (the ONLY way to update)
1. Make changes to skills, commands, or agents in `plugins/canopy/`
2. Bump the **patch version** in `plugins/canopy/.claude-plugin/plugin.json` (e.g. `0.2.6` → `0.2.7`)
3. Commit, merge to main, push:
   ```bash
   # From a worktree:
   git add -A && git commit -m "feat/fix: description"
   cd ~/emdash-projects/canopy && git merge <branch> && git push
   ```
4. **IMMEDIATELY after pushing**, run `/canopy:update` in the current session.
   This is mandatory — it pulls from GitHub, creates a new cache dir, and updates
   `installed_plugins.json`. Without it, the current session runs stale code while
   other sessions get the new version on next start. Do NOT skip this step.
5. Run `/reload-plugins` to activate the new version in the current session

New sessions auto-detect the version bump on startup — no manual steps needed.

### How it works
- `~/.claude/plugins/known_marketplaces.json` — marketplace entry pointing at this git repo
- `~/.claude/plugins/installed_plugins.json` — installed plugin entry with version + commit SHA
- Cache dir is keyed by version: `~/.claude/plugins/cache/canopy/canopy/<version>/`
- On session start, Claude Code pulls the marketplace repo and compares `plugin.json` version
  against the installed version — if different, it re-installs
- `/reload-plugins` only reloads skills from the existing cache — it does NOT detect
  version changes or re-install. That's why `/canopy:update` must run first.

## Testing
- `uv run pytest` from project root (420 tests)
