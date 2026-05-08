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
checked out in the main repo at `~/emdash-projects/canopy/`.
You CANNOT `git checkout main` from a worktree — it will fail.

To merge to main:
```bash
cd ~/emdash-projects/canopy && git merge <branch-name> && git push
```

If that fails with local changes, stash first:
```bash
cd ~/emdash-projects/canopy && git stash && git merge <branch-name> && git push
```

If remote is ahead, pull first:
```bash
cd ~/emdash-projects/canopy && git pull --rebase && git push
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
- `canopy observations list [--type T --status S --severity X --limit N --json-output]` — list observations
- `canopy observations show <id>` — show full YAML for one observation (id prefix accepted)
- `canopy proposals list [--status S --complexity X --limit N --json-output]` — list proposals
- `canopy proposals show <id>` — show full YAML for one proposal (id prefix accepted)
- `canopy skills list [--scope all|plugin|user --source PLUGIN --search TERM --json-output]` — list installed skills (JSON output includes `installed_version` + `cache_path` per entry)
- `canopy skills find <query> [--limit N --json-output]` — fuzzy-match installed skills by name and description; prints top matches with SKILL.md path. Use this before brainstorming a new skill ("do we already have one for X?").
- `canopy skills overlap <action text>` — check whether a proposed skill action duplicates an existing skill (exit 1 on overlap)
- `canopy skills budget [--scope ... --source ... --per-skill-limit N --aggregate-limit N --top N --json-output]` — show description-size budget (per-skill ranked table + aggregate gauge). Use when Claude Code prints "N skills dropped" and you need to know which skills are pushing the system prompt over the cap.
- `canopy skills dropped [--scope ... --source ... --per-skill-limit N --aggregate-limit N --json-output]` — simulate Claude Code's drop logic and print which skills get dropped under the aggregate cap.
- `canopy version verify` — confirm VERSION and plugin.json agree (CI-safe)
- `canopy version bump` — bump VERSION + plugin.json by `max(local, origin/main) + patch+1`. Fetches origin first so a parallel worktree's bump is visible before deciding the next number. Use this instead of editing the two files by hand.

## Key Modules

### Core pipeline
- `src/orchestrator/pipeline.py` — full improvement cycle (scanner discovery, circuit breaker, rate limiter)
- `src/orchestrator/analyzer.py` — transcript analysis via claude -p
- `src/orchestrator/proposer.py` — proposal generation via claude -p
- `src/orchestrator/implementer.py` — implementation via claude -p in target repos
- `src/orchestrator/skill_runner.py` — headless invocation of any Claude Code skill
- `src/orchestrator/paths.py` — shared CANOPY_DIR constant and legacy migration

### Data models
- `src/orchestrator/observations.py` — friction, gaps, patterns extracted from sessions
- `src/orchestrator/proposals.py` — improvement proposals with verification plans
- `src/orchestrator/campaigns.py` — multi-day improvement arcs
- `src/orchestrator/tracker.py` — proposal outcome tracking for self-improvement

### Intelligence
- `src/orchestrator/patterns.py` — cross-session pattern detection
- `src/orchestrator/briefing.py` — strategic brief with gstack cognitive patterns
- `src/orchestrator/router.py` — tiered routing (inline/single/team)
- `src/orchestrator/skill_catalog.py` — enumerates installed skills (plugin + user) and detects when a `new_skill` proposal duplicates one that already exists. Wired into the proposer prompt and `_validate_proposals` to silence the "we just proposed building something that already ships" pattern.

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

### CLI & utilities
- `src/orchestrator/cli.py` — Click CLI entry point
- `src/orchestrator/corpus.py` — activity corpus builder for analysis
- `src/orchestrator/digest.py` — daily digest generation from improvement runs
- `src/orchestrator/run_log.py` — improvement cycle run log tracking

### Plugin (Claude Code skills, commands, agents)
- `plugins/canopy/skills/` — skill definitions (select-session, improve, brief, patterns, orchestrator, product-management, doc-regeneration, update, walkthrough, walkthrough-defect-creator, walkthrough-eval, website-builder, auth-preflight, doctor, project-status)
- `plugins/canopy/commands/` — slash commands (pm-scout, pm-status, doc-regen, improve, brief, patterns, select-session, session-review, update, walkthrough, walkthrough-defect-creator, walkthrough-eval, website-builder, auth-preflight, project-status)
- `plugins/canopy/agents/` — autonomous agents (pm-supervisor, session-review, walkthrough, website-builder)
- `.claude-plugin/marketplace.json` — plugin marketplace manifest

## Important: Hook Must Use Stdlib Only
`hooks/post_tool_use.py` runs with system python3 which may not have PyYAML.
The repo map uses JSON (not YAML). Any hook code must use only stdlib modules.

## Skill Authoring: Bash Positional Parameters
Bash code blocks in skill/command markdown files must NOT use `$1`, `$2`, etc.
for function arguments. Claude Code's slash-command argument expansion strips
these before the shell sees them, causing silent failures (empty strings).

**Workaround:** Move complex bash logic to standalone scripts in `bin/` or
`scripts/` and invoke them from the skill. Simple inline commands (no functions)
are fine.

## Skill Authoring: Command/Skill Name Collisions

If `commands/<name>.md` AND `skills/<name>/SKILL.md` both exist, the Skill tool
silently resolves `canopy:<name>` to the slash-command file — the actual
SKILL.md never lands in context, and the agent improvises from memory.

**Rule:** colliding commands MUST follow Pattern B — read SKILL.md from disk
explicitly before following it:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/<name>/SKILL.md')"
```

Then `Read` that path and follow the SKILL.md exactly.

`tests/test_command_skill_collisions.py` enforces this — every colliding
command must reference `skills/<name>/SKILL.md` in its body. Adding a new
colliding command without Pattern B will fail CI.

## Skill Authoring: Built-in Command Namespace

Claude Code reserves a set of built-in slash command names (`/help`, `/clear`,
`/doctor`, `/config`, `/compact`, `/model`, `/fast`, `/login`, `/logout`,
`/agents`, `/mcp`, `/permissions`, etc.). Naming a plugin skill / command /
agent the same as a built-in causes a silent collision:

- `canopy:<name>` invocations route to the built-in handler, NOT your skill
- Worse, the entire skill description block can be truncated from the system
  prompt at session start — historically 142 skill descriptions vanished when
  `canopy:doctor` collided with native `/doctor`

**Rule:** before naming a new skill/command/agent, check whether the bare name
already works as a slash command in a stock Claude Code session. If yes, pick a
different name. The canonical fix when a native built-in lands on top of an
existing plugin entry is to namespace-prefix it (e.g. `doctor` →
`canopy-doctor`, shipped in v0.2.79).

`tests/test_builtin_command_collisions.py` enforces this — adding a new
plugin entry with a reserved name will fail CI. The reserved-set list lives
in that test; update it when Claude Code introduces new built-ins.

## Skill Authoring: Description Limits

Claude Code surfaces every installed skill's frontmatter `description` in the
system prompt at session start. Two budgets apply:

- **Per-skill cap**: Anthropic's authoring guidance recommends ≤1024 chars
  per description. Over the cap, Claude Code truncates.
- **Aggregate cap**: across all installed skills, the system prompt has a
  hard ceiling. Once it's hit, subsequent skills are dropped wholesale and
  Claude Code prints something like "N skills dropped" with no detail on
  which ones.

When a session reports dropped skills, run:

```bash
canopy skills budget               # ranked size table + aggregate gauge
canopy skills dropped              # simulated drop list under default caps
canopy skills dropped --aggregate-limit 30000   # try a different cap
```

The defaults (`--per-skill-limit 1024 --aggregate-limit 1500`) are
conservative — `--aggregate-limit` is the one to tune since the real
Claude Code ceiling is not publicly documented and shifts with releases.

## Cache Path Resolution

Plugin caches live at `~/.claude/plugins/cache/<plugin>/<plugin>/<version>/`
(double-nested by design — the inner dir name matches the outer plugin name).
The version segment changes every time the plugin is upgraded, so any path
constructed by string-concatenating a known version is fragile.

**Always derive the install path from `installed_plugins.json` instead of
hardcoding a version.** Canonical one-liner:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'])"
```

For the same shape per skill, use `canopy skills list --json-output` —
each entry now carries `installed_version` and `cache_path` fields. No more
string-concatenated versions.

## Tool Hygiene (Read, Bash, parallel calls)

A few repeat foot-guns that have shown up in session reviews:

- **Read before Edit, with absolute paths.** The Edit tool errors with "File
  has not been read yet" if you try to edit a file you haven't first read in
  the current session. Worktree-relative paths (`./src/foo.py`) sometimes
  resolve to a different file than the absolute path that Edit later asks
  for, so always Read with the absolute path you'll Edit with.
- **Bash parallel-call sibling cancellation.** When you fire several Bash
  tool calls in one turn, a sibling failure can silently cancel still-running
  calls and discard their output. If you need every result, run them
  sequentially or split across turns. Reserve parallel Bash for genuinely
  independent reads where partial loss is OK.
- **Don't extract YAML with awk/sed/grep.** Folded scalars (`>`, `|`),
  multi-line strings, and quoted block keys break naive line-based parsing
  and produce silent truncation. Use Python's `yaml.safe_load` instead:
  `python3 -c "import sys,yaml; d=yaml.safe_load(open(sys.argv[1])); print(d['description'])" path.md` (after stripping the frontmatter delimiters), or invoke a CLI that already does this (e.g. `canopy skills budget` for SKILL.md descriptions).
- **Don't dump binaries with `strings` / `cat`.** A multi-MB Mach-O dump in
  Bash output blows up your context. Pipe through `head -c 4000` or
  `xxd | head` if you really need a peek; otherwise use a real parser.

## Plugin Updates — NEVER locally patch

**CRITICAL: Never directly copy, rsync, or write files into `~/.claude/plugins/cache/`
or edit `~/.claude/plugins/installed_plugins.json` by hand.** This is "local patching"
and it bypasses the plugin system, creates version mismatches, and makes bugs hard to
diagnose. If you feel the urge to locally patch, STOP — use `/canopy:update` instead.

### ⛔ STOP — the #1 mistake: forgetting to bump VERSION

**If you change ANYTHING under `plugins/canopy/` (skills, commands, agents, the
`.claude-plugin/plugin.json` `description`, anything) you MUST bump the version.**

The version bump is the ONLY signal that tells installed sessions "there is new work to
pick up." Without it:

- `/canopy:update` reports `UP_TO_DATE` and refuses to sync the cache
- Every existing Claude session keeps running the OLD cached copy of your skill
- Your PR effectively didn't ship — you changed `main` but nobody will ever see it
- The version-sync CI check passes (it only checks VERSION and plugin.json match each
  other, NOT that you bumped). It will not save you.

**This is a ridiculous, silent failure mode.** If you merge a canopy PR without bumping,
you have essentially opened a PR and then quietly thrown the commit into a drawer. Worse,
you'll report to the user that the change is shipped and point them at `/canopy:update`
— which will then tell them there's nothing to update. Cue confusion.

**Mental checklist before EVERY canopy commit touching `plugins/canopy/`:**

1. Did I bump `VERSION`?
2. Did I bump `plugins/canopy/.claude-plugin/plugin.json`'s `version` to match?
3. Are the two numbers identical?

If any answer is no, amend the commit before pushing. Do not rely on the CI check — it
only verifies the two files match, it does NOT verify you actually incremented.

### Update workflow (the ONLY way to update)
1. Make changes to skills, commands, or agents in `plugins/canopy/`
2. Bump the **patch version** in BOTH `plugins/canopy/.claude-plugin/plugin.json` AND `VERSION` (e.g. `0.2.6` → `0.2.7`). See the STOP block above — this is the #1 mistake. A GitHub Actions check will fail if they don't match, but it will NOT catch a missing bump.
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

## Per-Project Canopy State

Per-project canopy state lives at `<repo>/.canopy/`, committed to the project's git repo:

- `<repo>/.canopy/pm/` — `canopy:product-management` state (autonomous.yaml, context.md, learnings.md, runs/). Resolved via `plugins/canopy/skills/product-management/scripts/resolve_pm_dir.sh` from any PM markdown file or agent.
- `<repo>/.canopy/lenses/` — per-project lens descriptors (PR #37).
- `<repo>/.canopy/run-artifacts.yaml`, `<repo>/.canopy/README.md` — project run-artifact map and onboarding.

Outside a git repo, the PM resolver falls back to `$HOME/.canopy/pm/<basename-of-cwd>/`.

The global "self-improvement brain" (`~/.claude/canopy/observations/`, `proposals/`, `session-log.jsonl`, etc.) stays under `$HOME/.claude/canopy/` — that data is intentionally cross-project on a single machine.

## Testing
- `uv run pytest` from project root (420 tests)
