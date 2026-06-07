# Canopy

Canopy is an autonomous self-improving system and Claude Code plugin. It watches
your Claude Code sessions across every project, identifies friction and capability
gaps, and ships improvements — to MCP servers, skills, hooks, workflows, CLAUDE.md
docs, or the orchestrator itself. It runs as a CLI (`canopy ...`) backed by a
Python orchestration pipeline, and as a Claude Code plugin that surfaces the same
machinery through skills, slash commands, and agents.

## What it does

Canopy closes a loop:

1. **Observe** — a Claude Code hook (`hooks/post_tool_use.py`) captures a session
   log and repo mappings as you work. The orchestrator parses transcripts and
   extracts observations (friction, gaps, recurring patterns).
2. **Propose** — observations are turned into improvement proposals, each with a
   verification plan. Proposals are checked against the existing skill catalog so
   canopy doesn't propose building something it already ships.
3. **Implement** — proposals are implemented via headless `claude -p` runs in the
   target repos, gated by a circuit breaker and rate limiter, and shipped as PRs.

It also generates strategic briefs, cross-session friction patterns, and a
browser UI for inspecting transcripts.

## Install / setup

Canopy installs as a Claude Code plugin from its marketplace. The fastest path on
a new machine is the bundled setup skill, which is idempotent:

```
/canopy:setup
```

This provisions the state directory, the main checkout, the capture hook, the
canopy-web workbench token, and the `canopy` CLI. To update an existing install
to the latest version from GitHub:

```
/canopy:update
```

For local development of the orchestrator itself:

```
uv run canopy --help          # CLI entry point (orchestrator.cli:main)
uv run pytest                 # test suite
```

Canopy targets Python 3.11+ and depends on PyYAML, Click, and Pydantic.

## Key concepts

- **The observe → propose → implement loop** is the core. `canopy improve` runs a
  full cycle; `--observe-only` and `--dry-run` stop after the earlier stages.
- **Two kinds of state.** Per-project state lives under `<repo>/.canopy/` and is
  committed to that project's git repo — e.g. `<repo>/.canopy/pm/` for
  product-management state and `<repo>/.canopy/lenses/` for per-project lenses.
  The global "self-improvement brain" (observations, proposals, the session log)
  lives under `$HOME/.claude/canopy/` and is intentionally cross-project on a
  single machine.
- **The plugin surface.** `plugins/canopy/` ships skills, slash commands, and
  agents — including the DDD (demo-driven-development) authoring pipeline, the
  product-management supervisor, portfolio review/guide, the alignment
  cross-system drift sweep, walkthrough rendering and eval, and the website
  builder. Skill descriptions are surfaced in the Claude Code system prompt, so
  canopy enforces description and naming budgets (see `canopy skills budget`,
  `canopy skills dropped`, and `canopy structure-drift`).
- **Always-PR shipping.** Changes ship as pull requests, and any change under
  `plugins/canopy/` must be accompanied by a version bump (`canopy version bump`)
  — the bump is the only signal that tells installed sessions to pick up new work.
  The full discipline lives in `CLAUDE.md`.

## CLI reference

Run `canopy <group> --help` for full flags. Grouped by purpose:

### Improvement pipeline
- `canopy improve` — run a full improvement cycle (analyze → propose → implement).
  `--observe-only` analyzes without proposing; `--dry-run` proposes without
  implementing.
- `canopy analyze <transcript.jsonl> [--propose]` — analyze a specific transcript.
- `canopy brief [--model MODEL]` — generate a strategic brief from recent activity.
- `canopy patterns [--json-output]` — show cross-session friction patterns.

### Observations & proposals
- `canopy observations list [...]` / `canopy observations show <id>` — inspect
  extracted observations.
- `canopy proposals list [...]` / `canopy proposals show <id>` — inspect generated
  proposals.
- `canopy verify-findings` — re-verify findings against the current state of their
  target repos, dropping any whose fix already shipped.

### Sessions & corpus
- `canopy sessions status` — session log entry count and classification summary.
- `canopy sessions list [--hours N] [--json-output]` — list recent sessions.

### Registry & discovery
- `canopy registry show [--format summary|skill|json]` — display the loaded
  capability registry.
- `canopy registry sync` — scan repos for actual MCP tools and update the registry.
- `canopy registry validate` — validate `registry.yaml` structure.
- `canopy portfolio-discover` — discover curated projects across the portfolio.

### Skills
- `canopy skills list [...]` — list installed skills (plugin + user).
- `canopy skills find <query>` — fuzzy-match installed skills by name/description.
- `canopy skills overlap <action text>` — check whether a proposed skill duplicates
  an existing one (exit non-zero on overlap).
- `canopy skills budget [...]` — show the description-size budget (per-skill table
  + aggregate gauge).
- `canopy skills dropped [...]` — simulate Claude Code's drop logic and list which
  skills get dropped under the aggregate cap.

### Health & versioning
- `canopy doctor [--json-output]` — diagnose plugin health (hook registration,
  session log, repo map, workbench token, plugin version). Exits non-zero on
  failure so it can gate CI.
- `canopy structure-drift [--strict] [--json-output]` — self-audit canopy's
  documented structural invariants (command/skill collisions, reserved-name
  collisions, version agreement across VERSION/plugin.json/marketplace.json,
  per-skill description budget).
- `canopy version verify` — confirm VERSION and plugin.json agree.
- `canopy version verify-bump` — confirm `plugins/canopy/` changes are accompanied
  by a version bump past origin/main.
- `canopy version bump` — bump VERSION + plugin.json to `max(local, origin/main) +
  patch+1`.

### Test hygiene
- `canopy test-audit collect` / `canopy test-audit apply` — audit and prune a
  pytest suite.

### Browser UI
- `canopy serve` — start the transcript browser web UI on localhost:8484 (a
  visibility tool, not the primary interface).

## Contributing

`CLAUDE.md` is the authoritative contributor and skill-authoring guide. It
documents the worktree rules, the always-PR + version-bump discipline, the git
hooks (`scripts/hooks/`), skill-authoring foot-guns (command/skill collisions,
reserved built-in names, description limits, bash positional-parameter gotchas),
plugin-update rules (never hand-patch the installed cache — use `/canopy:update`),
and the per-project `.canopy/` state layout. Read it before changing anything under
`plugins/canopy/` or the orchestrator.

Run the test suite with `uv run pytest` from the project root.
