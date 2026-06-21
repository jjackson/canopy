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

## Shipping Changes — always PR, then auto-merge (the maintainer does NOT review)

**Default workflow for every change: open a PR and merge it yourself.** The
maintainer does not review canopy PRs — opening one and waiting for review just
strands the work. So the PR is a record-keeping + CI step, not a review gate.

```bash
# from the worktree branch, once work is committed:
git push -u origin <branch>
gh pr create --title "..." --body "...\n\nCloses #<issue>"   # link the issue if any
gh pr merge <n> --merge                                       # auto-merge immediately
```

Then follow the plugin-update steps below (`/canopy:update` etc.) if
`plugins/canopy/` changed.

- **Always PR** (don't `git merge` straight to main) so CI runs and there's a
  durable record. The direct-merge commands above are the fallback for when
  `gh` is unavailable or a merge conflict needs hand-resolving in the main
  checkout — not the default.
- **Auto-merge — do not wait for review.** `gh pr merge --merge` right after
  creating the PR. The merge button isn't gated on CI for this private repo, so
  a red CI check won't block you; glance at the run, but the merge is yours to
  make.
- **Verify before merging** (this is the real gate, since no human reviews):
  the suite passes (or only known-unrelated failures remain) and — for
  `plugins/canopy/` changes — `canopy version verify` is green.
- Branch protection / required reviewers are NOT configured, so this is purely
  a discipline convention. Keep PRs scoped and the body honest about what was
  and wasn't verified.

## Tech Stack
- Python 3.11+, PyYAML, Click
- Claude Code hooks and skills
- Subprocess invocation of `claude -p` for analysis and proposals; proposal
  *implementation* is dispatched to Claude Code agents via `/canopy:improve` (the
  Python pipeline stops after proposals)

## Commands
- `canopy registry show [--format summary|skill|json]` — display loaded registry
- `canopy registry sync` — scan repos for actual MCP tools and update registry
- `canopy registry validate` — validate registry.yaml structure
- `canopy sessions status` — show session log entry count and classification summary
- `canopy sessions list [--hours N] [--json-output]` — list recent sessions
- `canopy create-agent <slug> --mandate "..." [--name --mailbox --stakeholders --into --force]` — scaffold a new Claude Code agent (its own git repo) from the operating model: persona, `turn` orchestrator, reads-free/writes-gated gating hook, canopy-web-ready layout. See `docs/agent-operating-model.md`.
- `canopy agent-publish {register|skills|sync|work} [--repo DIR ...]` — publish an agent repo to its canopy-web workspace (`/agents/<slug>`): register, mirror the skill catalog, post a sync, or push work products. Run from an agent repo root; identity resolved from its `.claude-plugin/plugin.json` + `config/agent.json`. The shared generalization of echo's `bin/echo_canopy.py`.
- `canopy agent-review <slug-or-path> [--hours N --no-llm --model --json-output]` — Build 2 of the operating model: review an agent's recent TURNS for friction (tool failures, retries, gating blocks, auth friction, checklist gaps) and synthesize ranked findings + fixes scoped to the agent repo. Deterministic signals always; `claude -p` synthesis unless `--no-llm`.
- `canopy harvest corpus <initiative> [--match terms --origin-k --recent-k --json-output]` — assemble a CROSS-USER, origin-anchored session corpus for one initiative (reads every readable `/Users/*/.claude/projects`), oldest-first, flagging `confidence: half-blind` if any user is unreadable. Deterministic material for Hal-as-architect to read + judge (intent reconstruction + drift are the agent's job, not this). See canopy memory `harvester-architect`.
- `canopy provision [--repo DIR --check --json-output]` — materialize an agent/provider repo's secrets from 1Password per its `config/secrets.yaml` (declarative refs + targets, no values). Portable across machines/operators/worktrees; idempotent; `--check` dry-runs. Backed by `src/orchestrator/provision.py`. See `docs/agent-operating-model.md` §4e.
- `canopy openclaw-harvest {snapshot|inventory|compare|bootstrap|reconcile}` — bridge a live OpenClaw into the fleet: snapshot its readable workspace (persona/skills/memory, NEVER creds), compare to the agent's GitHub repo, then bootstrap a new agent repo from it or reconcile its novel skills into the existing one. Engine is offline/testable; only `snapshot` needs ssh.
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
- `canopy version verify-bump` — fail if `plugins/canopy/` changed without a VERSION bump past origin/main (the check CI and the push guard run)
- `canopy version bump` — bump VERSION + plugin.json by `max(local, origin/main) + patch+1`. Fetches origin first so a parallel worktree's bump is visible before deciding the next number. Use this instead of editing the two files by hand.
- `canopy doctor` — diagnose canopy plugin health (workbench token, repo-map, session log, hook registration)
- `canopy shareout [...]` — gather a date range of sessions + PRs into a teammate-facing work briefing for the canopy-web /shareouts feed
- `canopy portfolio-discover` — list local emdash repos with recent activity that canopy can act on
- `canopy structure-drift` — self-audit canopy's documented structure against the actual tree (agent frontmatter, modules, docs)
- `canopy test-audit [...]` — build a test corpus for the agent to judge and prune dumb tests
- `canopy verify-findings` — re-verify session-review proposals against the current state of their target repos

## Key Modules

### Core pipeline
- `src/orchestrator/pipeline.py` — full improvement cycle (scanner discovery, circuit breaker, rate limiter)
- `src/orchestrator/analyzer.py` — transcript analysis via claude -p
- `src/orchestrator/proposer.py` — proposal generation via claude -p
- `src/orchestrator/skill_runner.py` — headless invocation of any Claude Code skill
- `src/orchestrator/paths.py` — shared CANOPY_DIR constant and legacy migration
- _No implementer module._ Proposal implementation is dispatched to Claude Code
  agents via the `/canopy:improve` skill; `pipeline.py` stops after saving
  proposals. (The old `claude -p` implementer was removed in `a6991a6` —
  "replace claude -p implementation pipeline with agent-based dispatch".)

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
- `src/orchestrator/skill_budget.py` — computes per-skill + aggregate description-size budget (backs `canopy skills budget` / `dropped`)
- `src/orchestrator/shareout.py` — gathers sessions + PRs over a date range into teammate-facing work briefings (backs `canopy shareout`)

### Registry & discovery
- `registry.yaml` — capability registry mapping servers to tools (auto-synced)
- `src/orchestrator/registry.py` — registry loader and validator
- `src/orchestrator/registry_sync.py` — scans @mcp.tool decorators from repos to keep registry accurate
- `src/orchestrator/scanner.py` — transcript discovery and metadata extraction
- `src/orchestrator/transcripts.py` — Claude Code transcript parsing
- `src/orchestrator/repo_map.py` — project-to-GitHub-repo mapping (JSON, stdlib only)
- `src/orchestrator/repo_paths.py` — resolves local repo checkout paths for a project
- `src/orchestrator/portfolio_discover.py` — discovers local emdash repos with recent activity (backs `canopy portfolio-discover`)

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
- `src/orchestrator/doctor.py` — canopy plugin health diagnostics (backs `canopy doctor`)
- `src/orchestrator/structure_drift.py` — self-audit of documented structure vs the actual tree (backs `canopy structure-drift`)
- `src/orchestrator/verify_findings.py` — re-verifies session-review proposals against current repo state (backs `canopy verify-findings`)
- `src/orchestrator/version_bump.py` — VERSION coordination across worktrees (backs `canopy version bump`)
- `src/orchestrator/agent_factory.py` — agent factory: stamps out a new agent repo from the operating-model templates (persona, turn, the config-driven gating hook). Backs `canopy create-agent`. Templates are embedded as the editable starting point every agent inherits. See `docs/agent-operating-model.md` (§4 Build 1, §4a topology).
- `src/orchestrator/agent_web.py` — canopy-web agent-workspace client (stdlib urllib): register an agent + mirror its skill catalog / post syncs / push work products to `/api/agents/*`. Slug-agnostic generalization of echo's `bin/echo_canopy.py`; backs `canopy agent-publish`. The "common" half of the §4a boundary — canopy owns the client, the agent repo owns only its identity (`config/agent.json`).
- `src/orchestrator/harvest.py` — harvest corpus engine (the deterministic half of Hal-as-architect): cross-user session discovery (`user_session_roots` walks `/Users/*`), origin-anchored initiative filtering (`find_initiative_sessions`, oldest-first), `assemble_corpus` (origin + recent slices, human-message extraction, `confidence` half-blind flag). NO judgment — intent/drift is the agent's native job. Backs `canopy harvest corpus`. See memory `harvester-architect`.
- `src/orchestrator/provision.py` — portable secret provisioning: reads a repo's `config/secrets.yaml` (1Password refs + targets, no values) and materializes each via `op` into its target (idempotent, 0600, `{repo}`/`~`/relative targets, `--check` dry-run). Backs `canopy provision`. 1Password = source of truth; worktree-clean (targets global or provider-repo, never a gitignored repo `.env`). See `docs/agent-operating-model.md` §4e.
- `src/orchestrator/openclaw_harvest.py` — OpenClaw → canopy-agent bridge: snapshot (rsync, excludes creds) + inventory + compare-to-repo + bootstrap-new / reconcile-novel-skills. Engine is pure/offline (testable); backs `canopy openclaw-harvest` + the `openclaw-harvest` skill. Salvages ideas off the dead OpenClaw droplets into git.
- `src/orchestrator/agent_review.py` — agent self-improvement lens (Build 2): finds an agent's recent turn transcripts (by cwd, across repo + worktrees), extracts deterministic friction signals (failures/retries/gating-blocks/auth/checklist-gaps), and runs an optional `claude -p` synthesis into ranked findings + fixes. Backs `canopy agent-review` + the `agent-review` skill. Reuses transcripts.py / repo_paths.py / the analyzer pattern — a lens on the existing loop, not a fork. See `docs/agent-operating-model.md` §4 Build 2.

### Plugin (Claude Code skills, commands, agents)
- `plugins/canopy/skills/` — skill definitions (alignment, auth-preflight, brief, canopy-doctor, agent-review, context-ingestion, create-agent, ddd-ace-render, ddd-concept-eval, ddd-evidence-audit, ddd-findings-review, ddd-narrative-actionability-eval, ddd-narrative-coherence, ddd-narrative-review, ddd-run, ddd-spec, ddd-spec-qa, ddd-upload, ddd-why-brief, ddd-why-eval, ddd-why-qa, doc-regeneration, find-session, improve, improve-lens, information-architecture, issue-triage, openclaw-harvest, orchestrator, patch-gstack-browse, patterns, portfolio-guide, portfolio-review, product-management, project-status, select-session, share-session, shareout, test-audit, update, verify-findings, visual-judge, walkthrough, walkthrough-defect-creator, walkthrough-eval, walkthrough-share, website-builder)
- `plugins/canopy/commands/` — slash commands (alignment, auth-preflight, brief, canopy-web-pat-mint, ddd, ddd-ace-render, ddd-concept-eval, ddd-evidence-audit, ddd-findings-review, ddd-narrative-actionability-eval, ddd-narrative-review, ddd-run, ddd-spec, ddd-spec-qa, ddd-upload, ddd-why-brief, ddd-why-eval, ddd-why-qa, doc-regen, find-session, improve, issue-triage, patch-gstack-browse, patterns, pm-autonomous, pm-autonomous-loop, pm-scout, pm-status, portfolio-guide, portfolio-review, project-status, select-session, session-review, setup, test-audit, update, verify-findings, walkthrough, walkthrough-defect-creator, walkthrough-eval, website-builder)
- `plugins/canopy/agents/` — autonomous agents (ddd, pm-supervisor, session-review, walkthrough, website-builder)
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

**Golden rule: never patch the installed plugin directly — always go through the
release flow.** There are three copies of canopy on a machine; only the first is editable:

| Location | What it is | May I edit it? |
|----------|------------|----------------|
| `plugins/canopy/` in **this repo** | Source of truth | ✅ **Yes — all changes start here** |
| `~/.claude/plugins/cache/canopy/canopy/<version>/` | The **installed** plugin Claude Code actually runs | ❌ **Never hand-edit** |
| `~/.claude/plugins/marketplaces/canopy/` | The update **channel** `/canopy:update` pulls from | ❌ Never edit/develop here |

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

**This is a ridiculous, silent failure mode.** PR #49 (silent video recording) merged
exactly this way: plugin files changed, VERSION was not bumped, the CI `check-version`
job failed and was visible in the PR UI — but the merge button isn't gated on it
(canopy is private, no GitHub Pro), so the PR went in anyway and `/canopy:update`
reported `UP_TO_DATE` forever after.

**The fix is layered prevention:**

1. **`canopy version bump`** — the only correct way to advance the version. Fetches
   origin/main, picks `max(local, origin/main) + patch+1`, writes both files atomically.
2. **Local pre-push hook** — refuses to push a branch where `plugins/canopy/` changed
   but VERSION didn't advance beyond origin/main. Catches the mistake before the PR
   is even opened. See § Git Hooks below — you must opt in with `git config core.hooksPath`.
3. **CI version-check workflow** — runs `canopy version verify-bump` on every PR.
   Visible in the PR UI but advisory only on private repos without GitHub Pro.

**Mental checklist before EVERY canopy commit touching `plugins/canopy/`:**

1. Did I run `uv run canopy version bump`? (It updates all THREE version files
   together — `VERSION`, `plugins/canopy/.claude-plugin/plugin.json`, and the two
   fields in `.claude-plugin/marketplace.json`. Editing them by hand is how
   marketplace.json drifted in the 0.2.157 bump — #120 changed only two files.)
2. Do all three agree? `VERSION` == `plugin.json` version == every
   `marketplace.json` version field. CI's version-check now fails on any mismatch.
3. Did the pre-push hook pass?

## Git Hooks

### Claude Code PreToolUse guard (auto-active, no opt-in) — the primary defense

Because **100% of canopy commits are AI-generated through Claude Code**, the
most reliable guard is a Claude Code `PreToolUse` hook, not a git hook. It is
checked into `.claude/settings.json` and loads automatically — no
`git config` step, works regardless of what emdash sets `core.hooksPath` to.

- `hooks/pre_tool_use_version_bump_guard.py` — intercepts any `git push` Bash
  call and runs the same `verify_bump_when_plugin_changed` check CI runs. If the
  branch touched `plugins/canopy/` without advancing VERSION past `origin/main`,
  it **denies the push** and hands the agent the exact fix (`canopy version
  bump`). This catches both failure modes that historically reddened CI: (A)
  forgot to bump, and (B) a parallel worktree already claimed your patch number.
  Override with `CANOPY_ALLOW_PUSH_NO_BUMP=1`.
- `hooks/pre_tool_use_plugin_cache_guard.py` — blocks local-patching of the
  plugin cache (`CANOPY_ALLOW_CACHE_PATCH=1` to override).

This is the only guard that fires in practice for AI-driven worktree flow — see
the git hooks below for why.

### Git hooks (opt-in, belt-and-suspenders) — dormant unless installed

Two hooks ship in `scripts/hooks/`. They are **inert until you opt in** with:

```bash
git config core.hooksPath scripts/hooks
```

In emdash worktrees `core.hooksPath` typically points at the main checkout's
default `.git/hooks` (which has no canopy hooks), and no human runs the opt-in —
so these never fired, which is exactly why CI kept catching missing bumps. The
Claude Code guard above supersedes them for the AI flow; keep these for humans.

- `pre-commit` — when `VERSION` or `plugins/canopy/.claude-plugin/plugin.json` is staged,
  runs `canopy version verify` to refuse a half-bump (one file edited, the other not).
- `pre-push` — refuses direct pushes to `main` AND runs `canopy version verify-bump`
  on the branch. Refuses the push if `plugins/canopy/` changed without VERSION
  advancing past origin/main.

Bypass either hook with `git push --no-verify` / `git commit --no-verify` — almost
always the wrong call. The hooks are advisory by design (no server-side enforcement
available without GitHub Pro), so discipline is the failure mode they protect against.

### Update workflow (the ONLY way to update)
1. Make changes to skills, commands, or agents in `plugins/canopy/`
2. Bump the **patch version** with `uv run canopy version bump` — do NOT hand-edit. It advances `VERSION`, `plugins/canopy/.claude-plugin/plugin.json`, AND both `.claude-plugin/marketplace.json` fields together (e.g. `0.2.6` → `0.2.7`). Hand-editing only two of the three is the drift that #120 introduced. See the STOP block above — a missing/partial bump is the #1 mistake. CI's version-check fails if the three disagree, but will NOT catch a missing bump on `main`.
3. Commit, push, PR, and auto-merge (see § Shipping Changes — the maintainer
   does NOT review; merge it yourself):
   ```bash
   # From a worktree:
   git add -A && git commit -m "feat/fix: description"
   git push -u origin <branch>
   gh pr create --title "..." --body "..."
   gh pr merge <n> --merge
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
- Releases are **version-on-`main`** — there are no git tags. "Released" means merged to
  `main` with the version bumped; `/canopy:update` is what distributes it.

## Per-Project Canopy State

Per-project canopy state lives at `<repo>/.canopy/`, committed to the project's git repo:

- `<repo>/.canopy/pm/` — `canopy:product-management` state (autonomous.yaml, context.md, learnings.md, runs/). Resolved via `plugins/canopy/skills/product-management/scripts/resolve_pm_dir.sh` from any PM markdown file or agent.
- `<repo>/.canopy/lenses/` — per-project lens descriptors (PR #37).
- `<repo>/.canopy/run-artifacts.yaml`, `<repo>/.canopy/README.md` — project run-artifact map and onboarding.

Outside a git repo, the PM resolver falls back to `$HOME/.canopy/pm/<basename-of-cwd>/`.

The global "self-improvement brain" (`~/.claude/canopy/observations/`, `proposals/`, `session-log.jsonl`, etc.) stays under `$HOME/.claude/canopy/` — that data is intentionally cross-project on a single machine.

## Repo Notes (DDD & rendering)

These ship in **this repo**, not the plugin cache:

- `scripts/ddd/` (DDD loop helpers). Skills resolve it via
  `DDD_REPO=$HOME/emdash-projects/canopy` (fallback
  `~/.claude/plugins/marketplaces/canopy`) and run `uv run python -m scripts.ddd.<mod>`.
- `scripts/narrative/` — the neutral narrative substrate (schemas, models,
  `${var}` substitution) extracted out of `scripts.ddd` so non-DDD callers can
  reuse it (PR #160, repointed in #162). DDD builds on top of it.
- `video-engine/` — the general Remotion video renderer, relocated into canopy
  (PR #191). Both the walkthrough and DDD render paths produce video through it;
  `render_locally.py` is the local entry point.
- DDD pause gates (`concept_change`, `external_release`, the narrative-agreement gate)
  post to the **canopy-web review surface**, never the built-in `AskUserQuestion` tool.
  See `plugins/canopy/agents/ddd.md` § Pause policy.

## Testing
- `uv run pytest` from project root (~1,900 tests across 137 test files). A handful of browser-dep tests error on collection unless the optional extras are installed: `pip install -e '.[browser]'`.
