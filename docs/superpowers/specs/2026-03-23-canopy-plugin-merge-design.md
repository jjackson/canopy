# Canopy Plugin Merge — Design Spec

**Date:** 2026-03-23
**Status:** Draft
**Goal:** Merge canopy-skills into canopy-orchestrator, rename to canopy, and expose the full orchestrator capability surface as Claude Code skills.

## Problem

canopy-orchestrator has 28 Python modules with powerful analysis, proposal, and implementation capabilities — but only 2 skills exposed to Claude Code. The PM and doc-regen skills live in a separate canopy-skills repo for no good reason. The result: a powerful engine with no hands inside Claude Code, and a split that makes maintenance harder.

## Solution

Merge canopy-skills into canopy-orchestrator. Rename to canopy. Add plugin scaffolding so the repo is a proper Claude Code plugin with skills, commands, and agents. Add new skills to expose the orchestrator's core capabilities.

## Repo Rename

| What | Before | After |
|---|---|---|
| GitHub repo | `jjackson/canopy-orchestrator` | `jjackson/canopy` |
| Python package name | `canopy-orchestrator` | `canopy` |
| CLI command | `orchestrator` | `canopy` |
| Plugin name | `canopy` (no change) | `canopy` |
| Marketplace | `canopy-skills` (separate repo) | `canopy` (this repo) |
| Python module dir | `src/orchestrator/` | `src/orchestrator/` (unchanged — rename later) |

The internal Python module stays `src/orchestrator/` to avoid touching every import across 28 modules + 411 tests. User-facing names change immediately.

## Directory Structure

Uses the marketplace pattern (Pattern A) matching the existing canopy-skills layout:

```
canopy/
├── .claude-plugin/
│   └── marketplace.json            # marketplace root — points to plugins/canopy/
├── plugins/
│   └── canopy/
│       ├── .claude-plugin/
│       │   └── plugin.json         # plugin metadata
│       ├── skills/
│       │   ├── select-session/
│       │   │   └── SKILL.md
│       │   ├── product-management/
│       │   │   ├── SKILL.md
│       │   │   └── templates/
│       │   │       ├── scout.md
│       │   │       └── implement.md
│       │   ├── doc-regeneration/
│       │   │   └── SKILL.md
│       │   ├── orchestrator/
│       │   │   └── SKILL.md
│       │   ├── improve/
│       │   │   └── SKILL.md
│       │   ├── brief/
│       │   │   └── SKILL.md
│       │   └── patterns/
│       │       └── SKILL.md
│       ├── commands/
│       │   ├── pm-scout.md
│       │   ├── pm-status.md
│       │   ├── doc-regen.md
│       │   ├── improve.md
│       │   ├── brief.md
│       │   └── patterns.md
│       └── agents/
│           └── pm-supervisor.md
├── src/orchestrator/               # Python engine (unchanged)
├── hooks/                          # Hooks (unchanged)
├── registry.yaml                   # Capability registry (unchanged)
├── pyproject.toml                  # Updated: name=canopy, entry point=canopy
├── docs/
└── tests/
```

The old `skills/` directory at repo root is deleted — all skills live under `plugins/canopy/`.

## Skill Surface

### Human-invoked skills

| Skill | Status | What it does |
|---|---|---|
| `select-session` | MOVE (from repo root skills/) | Menu-driven session picker → analyze |
| `product-management` | MOVE (from canopy-skills) | PM scout cycles with rotating lenses |
| `doc-regeneration` | MOVE (from canopy-skills) | Audit & regenerate CLAUDE.md |
| `orchestrator` | MOVE (from repo root skills/) | Cross-project query routing via registry |
| `improve` | NEW | Full improvement cycle (analyze → propose → implement) |
| `brief` | NEW | Strategic brief from recent activity |
| `patterns` | NEW | Cross-session friction pattern detection |

### Slash commands

| Command | Status | Maps to |
|---|---|---|
| `/pm-scout` | MOVE | product-management skill |
| `/pm-status` | MOVE | product-management skill (status mode) |
| `/doc-regen` | MOVE | doc-regeneration skill |
| `/improve` | NEW | improve skill |
| `/brief` | NEW | brief skill |
| `/patterns` | NEW | patterns skill |

### Agents

| Agent | Status | What it does |
|---|---|---|
| `pm-supervisor` | MOVE | Autonomous PM cycle for open claws |

## New CLI Commands

Two new CLI commands to back the new skills:

### `canopy brief`

Wraps `briefing.py`:
```
canopy brief [--model MODEL] [--budget BUDGET]
```
Generates a strategic brief from recent runs, patterns, and track record. Outputs markdown.

### `canopy patterns`

Wraps `patterns.py`:
```
canopy patterns [--json-output]
```
Shows recurring issues and project hotspots from observations. Default: human-readable table. `--json-output`: JSON for skill consumption.

### Existing commands (renamed)

All existing `orchestrator` commands become `canopy` commands:
- `canopy improve`
- `canopy analyze <transcript>`
- `canopy sessions list`
- `canopy sessions status`
- `canopy registry show|sync|validate`
- `canopy serve`

## New Skill Designs

### `/improve` skill

```markdown
---
name: improve
description: Run a full canopy improvement cycle — analyze recent sessions, propose improvements, and optionally implement them
version: 0.1.0
---

Runs the canopy improvement pipeline on recent Claude Code sessions.

## Arguments
- No args: full cycle (analyze + propose + implement)
- `observe`: analyze only, no proposals
- `dry-run`: analyze + propose, no implementation

## Flow
1. Run `uv run canopy improve [--observe-only|--dry-run]` from ~/emdash-projects/canopy (or current worktree)
2. Show progress as it runs
3. Display results: transcripts analyzed, observations, proposals, implementations
```

### `/brief` skill

```markdown
---
name: brief
description: Generate a strategic brief from recent canopy activity — patterns, success rates, and improvement opportunities
version: 0.1.0
---

Generates a CEO-level strategic brief from recent orchestrator activity.

## Flow
1. Run `uv run canopy brief` from ~/emdash-projects/canopy
2. Display the markdown output
```

### `/patterns` skill

```markdown
---
name: patterns
description: Show cross-session friction patterns — recurring issues and project hotspots detected across Claude Code sessions
version: 0.1.0
---

Shows aggregated patterns from session analysis.

## Flow
1. Run `uv run canopy patterns` from ~/emdash-projects/canopy
2. Display recurring issues ranked by frequency
3. Display project hotspots by server
```

## pyproject.toml Changes

```toml
[project]
name = "canopy"

[project.scripts]
canopy = "orchestrator.cli:main"
```

Remove old `orchestrator` entry point.

## Migration Steps

### 1. Rename package
- Update pyproject.toml: name → `canopy`, entry point → `canopy`
- Update cli.py docstring: "Orchestrator" → "Canopy"
- This goes first so all subsequent content can reference `canopy` CLI immediately

### 2. Plugin scaffolding
- Create `.claude-plugin/marketplace.json` at repo root
- Create `plugins/canopy/.claude-plugin/plugin.json`
- Follows Pattern A (marketplace pattern) matching existing canopy-skills layout

### 3. Move canopy-skills content
- Copy skills, commands, agents, templates from `~/.claude/plugins/marketplaces/canopy-skills/plugins/canopy/` into `plugins/canopy/`
- Update all references: `uv run orchestrator` → `uv run canopy`
- Update all working directory refs: `~/emdash-projects/canopy-orchestrator` → `~/emdash-projects/canopy`

### 4. Move repo-local skills
- Move `skills/orchestrator/` and `skills/select-session/` into `plugins/canopy/skills/`
- Update their `uv run orchestrator` references to `uv run canopy`
- Delete old `skills/` directory

### 5. Create new skills + commands
- Write `plugins/canopy/skills/improve/SKILL.md`, `brief/SKILL.md`, `patterns/SKILL.md`
- Write `plugins/canopy/commands/improve.md`, `brief.md`, `patterns.md`

### 6. Add new CLI commands
- Add `canopy brief` command to cli.py (wraps `briefing.generate_brief()`)
- Add `canopy patterns` command to cli.py (wraps `patterns.detect_patterns()`)
- Add tests for both new commands

### 7. Update CLAUDE.md
- Rename all `orchestrator` CLI references to `canopy`
- Update repo description and commands section

### 8. Plugin registration
- Uninstall old: `claude plugin uninstall canopy@canopy-skills`
- Register new marketplace pointing at `jjackson/canopy` (or local path during dev)
- Install: `claude plugin install canopy@canopy`
- Plugin identifier changes from `canopy@canopy-skills` to `canopy@canopy`

### 9. Verify
- Run `uv run pytest` — all tests pass
- Verify `canopy` CLI works: `uv run canopy --help`
- Start new Claude Code session, verify all skills appear in `/` autocomplete
- Test `/select-session`, `/improve`, `/brief`, `/patterns`

### 10. Cleanup
- Archive `jjackson/canopy-skills` repo on GitHub
- Remove select-session copy from old canopy-skills plugin cache at `~/.claude/plugins/marketplaces/canopy-skills/`

## Path during transition

Until the GitHub repo is renamed, the working directory remains `~/emdash-projects/canopy-orchestrator`. Skills should reference the canopy CLI command (`uv run canopy`) which works regardless of directory name. After the GitHub rename, emdash worktrees will use the new name. Update skill working directory references at that point.

## What's NOT in scope

- Renaming Python module `src/orchestrator/` → `src/canopy/` (separate task, touches every import)
- GitHub repo rename via API (manual step — do after merge, then update skill working dir refs)
- New skills beyond improve/brief/patterns (add later as needed)
