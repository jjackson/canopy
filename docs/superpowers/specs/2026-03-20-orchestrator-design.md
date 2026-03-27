# Canopy Orchestrator — Design Document

**Date:** 2026-03-20
**Status:** Draft

## Problem

Jonathan has 6+ projects with MCP servers in `~/emdash-projects/`, each with
tools for different parts of the Connect ecosystem. Today these tools work in
isolation — there's no system that watches how they're used together, identifies
what's missing, and builds new capabilities automatically.

The primary workflow — taking a vague program idea through research,
solicitation, evaluation, award, app improvement, training material creation,
and program execution — spans many sessions and many MCP servers. Significant
parts of this lifecycle have no tooling at all. Building those missing pieces
manually is slow, and knowing *what* to build requires observing real usage
patterns across sessions.

**Inspiration:**
- [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) — autonomous improvement loop: hypothesize → modify → evaluate → keep/discard
- [Intercom's Claude Code system](https://x.com/brian_scanlan/status/2033978300003987527) (Brian Scanlan) — 13 plugins, 100+ skills, SessionEnd transcript analysis, gap classification, feedback loop into GitHub issues

## Solution

**Canopy Orchestrator** is a self-improving orchestration layer that sits on top
of Claude Code and the MCP ecosystem. It operates autonomously:

1. **Observes** — passively captures everything across all projects via hooks
   and transcript analysis
2. **Analyzes** — identifies friction, gaps, failures, and missing capabilities
   by examining session transcripts
3. **Evolves** — uses Claude Code to implement improvements and merges them into
   the ecosystem automatically

The goal is full autonomy. For self-owned repos, it implements and auto-merges.
For team repos, it opens PRs. It tells you what it did, not asks what to do.
Over time, more of the Connect program lifecycle (and other workflows) should
"just work" because the orchestrator has been watching and filling gaps.

The system generates a daily digest of what it observed, what it improved, and
what it's planning next — providing visibility without requiring supervision.

**It is not:**
- A router that picks the right tool (Claude's own reasoning does that via skill
  context)
- A replacement for Claude Code (it directs Claude Code, doesn't replicate it)

## Architecture

### Four Subsystems

**Subsystem 1 — Capture** *(built)*

PostToolUse hook logs every MCP tool call across all Claude Code sessions to
`~/.claude/canopy/session-log.jsonl`. Captures: server, tool, inputs
(truncated), success/failure, session ID, project. Runs globally — every
session, every project.

**Subsystem 2 — Transcript Analyzer**

Reads full Claude Code transcripts after sessions end. Extracts structured
observations:

- **Friction**: tool calls that failed, required retries, or produced unhelpful
  results
- **Gaps**: moments where work was done manually that could have been a tool
- **Patterns**: recurring multi-tool sequences that could become a workflow
- **Missing capabilities**: things that were asked for that no MCP server,
  skill, or hook could handle

Stores observations in `~/.claude/canopy/observations/` as structured
YAML files. This is the "eyes" of the system — everything downstream depends on
the quality of this analysis.

**Transcript discovery:** Claude Code stores session transcripts in
`~/.claude/projects/<mangled-project-path>/` as JSONL files. The capture hook's
session log provides session IDs and project paths that map to transcript
locations. The existing `find_transcript_path()` in `capture.py` constructs
these paths. To find transcripts since the last run, the orchestrator:

1. Reads the session log for entries since the last run timestamp
2. Groups by session ID to get unique sessions
3. Resolves each to a transcript path via `find_transcript_path()`
4. Skips any transcript still being written (detected via file modification
   time staleness — if the file was modified within the last few minutes, it
   may still be active)

**Note:** Claude Code's transcript storage format is not a public API. If it
changes, transcript discovery is the only component that breaks — observations
and everything downstream are format-independent.

**Subsystem 3 — Proposal Engine**

Takes observations from the analyzer and generates concrete improvement
proposals:

- **New tool**: "Add `generate_training_manual` to connect-labs"
- **New server**: "Create a training-materials MCP server"
- **Tool improvement**: "Add status filter to `search_opportunities`"
- **New skill**: "Create a solicitation-evaluation skill"
- **New workflow**: "Codify the solicitation → evaluation → award sequence"
- **Hook improvement**: "Add a PreToolUse gate for write operations"
- **Registry update**: "Add answers/tools entries for new capabilities"

Each proposal includes: what to change, which repo, why (linked to
observations), and estimated complexity. For `self`-owned repos, proceeds to
implementation automatically. For `team` repos, creates a PR with context.

**Subsystem 4 — Implementation & Integration**

Uses Claude Code as the implementation engine. Spawns headless Claude Code
sessions via subprocess with `cwd` set to the target repo:
`claude -p "<prompt>" --allowedTools "..."`. Provides via the prompt:

- The proposal (what to build)
- The observation (why it's needed)
- The registry context (what already exists)
- The repo conventions (from that project's CLAUDE.md)

Claude Code handles the rest: reading the codebase, writing code, running tests,
committing. The orchestrator captures stdout/exit code to determine success.
After implementation:

- Updates `registry.yaml` with new capabilities
- Updates the skill context so future sessions know about the new tools
- Writes to the run log

The orchestrator itself stays simple — it's a pipeline coordinator, not a code
generator. The intelligence is in the prompts it constructs and the data it
feeds to Claude Code.

### What Gets Improved

The orchestrator can propose and implement improvements to anything in the
ecosystem:

| Target | Examples | Where it lives |
|---|---|---|
| MCP tools | New endpoints, better schemas, missing parameters, bug fixes | Individual project repos |
| MCP servers | Entirely new servers for unmet needs | New repo or added to existing |
| Skills | New Claude Code skills, improved skill context, better guidance | canopy-skills or project-local |
| Hooks | New capture hooks, quality gates, post-session analysis | canopy-orchestrator or global settings |
| Workflows | Codified multi-step sequences, trigger phrases | registry.yaml |
| Registry | New server/tool entries, updated `answers` fields | canopy-orchestrator |
| The orchestrator itself | Better analysis prompts, smarter proposals, new observation categories | canopy-orchestrator |

### Ownership Model

How changes land depends on who owns the target:

- **`self`** (your repos) — implement and auto-merge, notify via digest
- **`team`** (shared repos) — implement and open PR with context
- **`external`** (third-party) — registry-only update, note the limitation

### Safety Model

Autonomous systems need guardrails:

- **Tests must pass** — implementation sessions run tests before committing. If
  tests fail, the proposal is marked as failed and logged, not retried
  automatically.
- **Branch-then-merge** — implementations land on a feature branch first, then
  merge to main only after tests pass. This preserves a revert path.
- **Max proposals per cycle** — each run implements at most 3 proposals to
  limit blast radius. Remaining proposals queue for the next run.
- **Self-targeting proposals require extra caution** — changes to the
  orchestrator's own prompts, analysis logic, or proposal engine go through a
  dry-run comparison (run the new version against recent transcripts and compare
  output quality) before merging.
- **Rollback** — every auto-merged change is a discrete commit on a branch.
  If a downstream problem is detected, `git revert` on the specific commit
  is sufficient.

## The Improvement Loop

### Concrete Example

**You do a session:** You're creating a solicitation for a new health program.
You search for context, explore the app structure, draft the solicitation. But
when it comes time to create training materials for the workers who'll respond,
there's nothing — you end up writing it manually.

**Capture** picks up the tool calls: `connect-search.search_documents`,
`commcare-hq.get_app_structure`, `solicitations.create_solicitation`. All
succeeded.

**Transcript Analyzer** reads the full conversation and notices:
- You asked Claude to help create training materials
- Claude had no MCP tool for this
- You spent significant time doing it manually
- The content drew heavily on the app structure data that `commcare-hq` had
  already provided

It creates an observation:
```yaml
type: gap
description: "No tool for generating training materials from app structure"
severity: high
frequency: 1
sessions: ["abc123"]
related_servers: ["commcare-hq"]
lifecycle_stage: "training-material-creation"
```

**Proposal Engine** generates:
```yaml
type: new_tool
target_repo: "~/emdash-projects/connect-labs"
ownership: self
action: "Create generate_training_manual tool in the commcare MCP server"
motivation: "Session abc123: user manually created training materials using
  app structure data that was already available via commcare-hq"
complexity: medium
```

**Implementation** spawns a Claude Code session in `connect-labs`:
- Reads existing MCP server structure
- Implements the new tool
- Writes tests
- Auto-merges
- Updates `registry.yaml` with the new tool entry
- Updates the skill context

**Next time** you create a solicitation, the training material tool is
available. The orchestrator notices you used it and it worked — that observation
reinforces the improvement.

### Single Improvement Cycle

A single run of the pipeline:

1. **Collect** — find all Claude Code transcripts since last run
2. **Analyze** — for each transcript, extract observations using Claude as the
   analyzer
3. **Deduplicate** — merge with existing observations (same gap seen 5 times =
   high priority, not 5 separate proposals). Matching is LLM-assisted: Claude
   compares new observations against existing ones, considering `type`,
   `related_servers`, and `lifecycle_stage`. Matches increment frequency and
   append session references. Novel observations create new entries.
4. **Prioritize** — rank observations by frequency, severity, and how much of
   the Connect lifecycle they'd unlock
5. **Propose** — for the top N observations, generate concrete improvement
   proposals
6. **Implement** — spawn Claude Code sessions to execute each proposal against
   the target repo
7. **Integrate** — update registry, skill context, and corpus to reflect new
   capabilities
8. **Report** — write run log, update daily digest

## Execution Model

### Manual Trigger

For testing and development:

```
orchestrator improve                    # full cycle
orchestrator improve --observe-only     # just analyze, don't propose/implement
orchestrator improve --dry-run          # propose but don't implement
```

### Scheduled Runs

Uses Claude's scheduled commands to run the full cycle 2-3x daily. Each run:

- Scans transcripts since the last run
- Writes results to a run log
- If it implemented something, the digest includes what changed and why

### Cost Management

Each cycle involves multiple Claude Code invocations (transcript analysis,
proposal generation, implementation). To keep costs bounded:

- **Max transcripts per run**: analyze the 10 most recent unprocessed
  transcripts. Remaining ones queue for the next run.
- **Max proposals per cycle**: implement at most 3 per run.
- **Analysis batching**: short transcripts (< 50 tool calls) can be batched
  into a single analysis call.
- **Processed transcript tracking**: each run records which transcripts it
  analyzed so they're not re-processed.
- **Per-session budget cap**: implementation sessions use `--max-budget-usd`
  to cap individual Claude Code invocations.

### Run State

```
~/.claude/canopy/
├── session-log.jsonl          # raw capture (exists)
├── observations/              # structured observations from transcript analysis
├── proposals/                 # improvement proposals (pending, implemented, rejected)
├── runs/                      # run logs (one per cycle)
└── digest.md                  # current daily digest
```

**Note on existing corpus module:** The Phase 1 `corpus.py` module stores
evaluation corpus entries (goal, expected tool sequences, outcomes) — these are
test cases for validating orchestration quality. The observations store
introduced here is a separate data model (friction/gaps/patterns extracted from
transcripts). Both live under the orchestrator but serve different purposes:
observations drive improvement proposals, corpus entries validate that
improvements work.

## How It Uses Claude Code

The orchestrator doesn't contain implementation logic — it directs Claude Code
to do the work. Each stage of the pipeline is a Claude Code interaction:

**Transcript analysis** — Claude reads a transcript and produces structured
observations. The orchestrator provides the prompt template and the transcript,
Claude does the reasoning.

**Proposal generation** — Claude takes observations + registry context and
proposes specific improvements. It knows what exists (from the registry) and
what's missing (from observations).

**Implementation** — Claude Code session in the target repo. The orchestrator
provides the proposal, the observation, the registry context, and the repo
conventions. Claude Code reads the codebase, writes code, runs tests, commits,
and merges.

## Phases

**Phase 1 — Foundation** *(done)*
- Registry, capture hook, corpus structure, CLI, skill
- MCP tools work across projects with registry-guided routing

**Phase 2 — The Loop**
- Full observe → propose → implement pipeline
- Manual trigger: `orchestrator improve` kicks off a cycle
- Scheduled: runs automatically 2-3x/day via Claude's scheduled commands
- Each run: scan transcripts → extract observations → generate proposals →
  implement and merge
- Daily digest of what changed

**Phase 3 — Self-Improvement**
- The orchestrator applies the loop to itself
- Tracks which observations led to useful proposals, which proposals succeeded
- Improves its own analysis and proposal quality over time
- Self-targeting proposals use dry-run comparison: run the proposed change
  against recent transcripts and compare output quality before merging

**Phase 4 — HTTP Gateway & UI**
- Web interface for non-engineers to trigger workflows
- Dashboard: what servers exist, what's been improved, what's planned
- Digest becomes a visual dashboard

## Primary Use Case: Connect Program Lifecycle

The Connect lifecycle drives development. Current state and gaps:

```
Vague idea + articles ──→ Deep research on solicitation approaches
  [connect-search: exists]

──→ Study example Connect/CommCare apps
  [commcare-hq: exists]

──→ Design and release solicitation
  [solicitations: exists]

──→ Evaluate responses that come back
  [GAP: no tooling]

──→ Award solicitation
  [GAP: no tooling]

──→ Get feedback on app/program design
  [GAP: no tooling]

──→ Improve the app based on feedback
  [GAP: no tooling]

──→ Generate training materials
  [GAP: no tooling]

──→ Run the program through Connect
  [scout-data for monitoring: exists]
```

The orchestrator's job is to progressively fill these gaps by watching you work
through the lifecycle manually and building the missing pieces.

## Key Design Decisions

- **Full autonomy is the goal** — the system implements and merges, not just
  suggests. Human approval is a fallback, not the default.
- **Claude Code is the implementation engine** — the orchestrator coordinates,
  Claude Code builds. This keeps the orchestrator simple and leverages Claude
  Code's existing strength.
- **PostToolUse hook logs machine-readable fields only** — intent is inferred
  later by the transcript analyzer, not captured at call time.
- **Ownership model governs merge strategy** — `self`=auto-merge,
  `team`=PR, `external`=registry-only.
- **The improvement target is the entire ecosystem** — MCP servers, skills,
  hooks, workflows, registry, and the orchestrator itself. Anything that makes
  sessions more effective is fair game.
- **Observations deduplicate and compound** — the same gap seen across multiple
  sessions increases priority, not proposal count.
- **The Connect lifecycle is the primary driver** — but the system is
  general-purpose and applies to any workflow across Jonathan's projects.
