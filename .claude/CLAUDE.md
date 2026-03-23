# Canopy Orchestrator

Self-improving MCP orchestration system. Composes MCP servers across projects,
learns from usage patterns, and auto-evolves tools via autoresearch.

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

## Commands
- `orchestrator registry show [--format summary|skill|json]` — display loaded registry
- `orchestrator registry validate` — validate registry.yaml structure
- `orchestrator sessions status` — show session log entry count and classification summary
- `orchestrator improve` — run a full improvement cycle (analyze → propose → implement)
- `orchestrator improve --observe-only` — analyze transcripts without proposing
- `orchestrator improve --dry-run` — analyze and propose without implementing
- `orchestrator serve` — start transcript browser web UI on localhost:8484
- `orchestrator analyze <transcript.jsonl> [--propose]` — analyze a specific transcript

## Key Files
- `registry.yaml` — capability registry mapping MCP servers to their tools
- `src/orchestrator/registry.py` — registry loader and validator
- `src/orchestrator/capture.py` — session log writer (PostToolUse hook logic)
- `src/orchestrator/transcripts.py` — Claude Code transcript discovery and parsing
- `src/orchestrator/observations.py` — observation data model (friction, gaps, patterns)
- `src/orchestrator/proposals.py` — improvement proposal data model
- `src/orchestrator/analyzer.py` — transcript analysis via claude -p
- `src/orchestrator/proposer.py` — proposal generation via claude -p
- `src/orchestrator/implementer.py` — implementation via claude -p in target repos
- `src/orchestrator/pipeline.py` — full improvement cycle orchestration (scanner-based discovery, circuit breaker, rate limiter)
- `src/orchestrator/skill_runner.py` — headless skill invocation (any plugin: gstack, superpowers, etc.)
- `src/orchestrator/circuit_breaker.py` — stops pipeline after consecutive failures
- `src/orchestrator/rate_limiter.py` — caps API calls per hour
- `src/orchestrator/patterns.py` — cross-session pattern detection
- `src/orchestrator/briefing.py` — strategic brief with gstack cognitive patterns
- `src/orchestrator/tracker.py` — self-improvement tracking (proposal outcomes)
- `src/orchestrator/router.py` — tiered routing (inline/single/team)
- `src/orchestrator/campaigns.py` — campaign persistence for multi-day improvement arcs
- `src/orchestrator/scheduler.py` — persistent scheduling via launchd
- `src/orchestrator/server.py` — HTTP server for transcript browser
- `src/orchestrator/scanner.py` — transcript discovery and metadata extraction
- `src/orchestrator/labels.py` — transcript label storage
- `src/orchestrator/repo_map.py` — project-to-GitHub-repo mapping
- `src/orchestrator/reviewer.py` — AI strategic review via claude -p
- `src/orchestrator/static/index.html` — transcript browser frontend
- `hooks/post_tool_use.py` — Claude Code hook for session capture
- `skills/orchestrator/SKILL.md` — Claude Code skill for cross-project routing

## Testing
- `pytest` from project root
