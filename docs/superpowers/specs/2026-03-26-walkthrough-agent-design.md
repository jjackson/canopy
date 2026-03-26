# Walkthrough Agent Design

**Date:** 2026-03-26
**Status:** APPROVED

## Problem

The walkthrough skill is a 630-line monolith covering four modes: run, improve,
adversarial, and generate. The `improve` and `adversarial` modes are orchestration
logic — they run the walkthrough, analyze scores, dispatch specialist skills, and
iterate until convergence. This is agent behavior shoehorned into a skill.

The skill also starts from scratch every session. It has no memory of which scenes
tend to break, what the user considers acceptable scores, or what specialist skills
have found before. The JSON sidecar provides run-to-run comparison, but only within
a single project — there's no cross-session learning.

## Solution

Split the walkthrough into an agent + skill with clear responsibilities:

- **Agent** (`agents/walkthrough.md`): Orchestrates improve/adversarial/eval modes,
  manages persistent memory, tracks eval history, makes iteration decisions.
- **Skill** (`skills/walkthrough/SKILL.md`): Core run procedure — setup, scene
  execution, 5-dimension scoring, deck generation. Deterministic pipeline.
- **Command** (`commands/walkthrough.md`): Routes modes to agent or skill.

## Architecture

### File Layout

```
plugins/canopy/
├── agents/walkthrough.md           — orchestrator agent
├── skills/walkthrough/SKILL.md     — core run procedure (trimmed)
└── commands/walkthrough.md         — command router
```

### Command Routing

| Command | Routes to | Why |
|---------|-----------|-----|
| `/walkthrough <name>` | Skill | Deterministic run — no orchestration needed |
| `/walkthrough generate` | Skill | Interactive spec creation — no orchestration |
| `/walkthrough` (no args) | Skill | List specs — trivial |
| `/walkthrough improve <name>` | Agent | Orchestrates run + specialist dispatch + rerun loop |
| `/walkthrough adversarial <name>` | Agent | Orchestrates run + parallel adversarial passes |
| `/walkthrough eval <name> [flags]` | Agent | Run + score + baseline comparison + history |

### Skill (Core Run Procedure)

The skill shrinks from ~630 to ~350 lines. It retains:

1. **Preamble** — canopy update check
2. **YAML spec format** — spec documentation and examples
3. **Setup** — browse binary, state file, spec read, previous run check, output dirs, auth
4. **Pre-flight check** — verify app is healthy before capturing
5. **Scene execution** — navigate, wait, screenshot, 5-dimension scoring, blocking rule
6. **Data collection** — JSON structure with base64 screenshots
7. **Presentation generation** — find and run generate_presentation.py
8. **Deck verification** — open deck in browse, verify slides match scores
9. **Generate mode** — interactive spec creation
10. **Efficient reruns** — selective retake, screenshot reuse

What the skill removes:

- Improve mode (steps 1-4) — moves to agent
- Adversarial mode (steps 1-4) — moves to agent
- Iteration loop section (orchestration logic) — moves to agent
- Prioritized action list + user interaction — moves to agent
- Mode listing from header (agent modes documented in agent instead)

The skill's description changes to reflect its focused scope — it runs walkthroughs,
it doesn't orchestrate improvement cycles.

### Agent (Orchestrator)

The agent owns all multi-step orchestration. It follows the website-builder pattern:
frontmatter with `memory: user`, clear identity, staged pipeline, persistent memory.

#### Frontmatter

```yaml
---
name: walkthrough
description: >
  Orchestrate demo walkthrough improvement cycles. Runs the walkthrough skill,
  analyzes scores, dispatches specialist skills to fix failing dimensions,
  reruns until convergence. Tracks eval history and learns from past sessions.
  Use for "walkthrough improve", "walkthrough adversarial", or "walkthrough eval".
model: inherit
memory: user
---
```

#### Persistent Memory

```
~/.claude/agent-memory/walkthrough/
├── MEMORY.md                    — index of all memories
├── project-<name>.md            — per-project: known scene issues, data quirks
├── scoring-calibration.md       — what the user considers acceptable
└── specialist-results.md        — patterns from /review, /design-review, /qa
```

Memory accumulates over time:

- **Project memories:** "Scene 4 in baobab-demo breaks when payment data is missing —
  check data before running." "Scene 2 needs a worktree CSS build or it renders unstyled."
- **Scoring calibration:** "User considers 3/5 on App Page Quality acceptable for internal
  demos but requires 4+/5 for external stakeholders." "User thinks my Content scoring
  is too lenient — be harsher on generic AI output."
- **Specialist results:** "The /review skill consistently finds prompt injection issues
  in report agents." "/design-review usually fixes 2-3 spacing issues per page."

The agent reads MEMORY.md at startup and uses it to inform routing decisions.

#### Improve Mode

The agent's primary mode. Orchestration flow:

**Step 1: Context + Run**
1. Read agent memory for project-specific notes
2. Invoke the walkthrough skill to run the spec (all scenes, full scoring)
3. Read the resulting JSON sidecar for scores

**Step 2: Analyze + Route**

After the skill returns scores, check each dimension across all scenes.
For any dimension averaging ≤ 3/5 or with any scene scoring ≤ 2:

| Dimension | Route to | What it does |
|-----------|----------|-------------|
| Content Quality | `/review` | Adversarial code review of AI content generators |
| App Page Quality | `/design-review` | Live site visual audit, atomic fix commits |
| Screenshot Quality | Self-fix | Adjust browse commands (viewport, scroll, DOM) |
| Slide Quality | Self-fix | Improve narration in spec, adjust framing |
| Demo Readiness | `/qa` | Systematic QA of failing pages, fix commits |

Present a prioritized action list before dispatching:

```
## Suggested Actions (highest impact first)

1. [CODE] Scene 4 "AI Report": AI cites "$0-5 per visit"
   Impact: Stakeholder would question data accuracy
   Dimensions: Content (2/5), Demo Readiness (2/5)

2. [DATA] Scene 1 "Fund Dashboard": Budget shows "---"
   Impact: First impression slide looks broken
   Dimensions: Content (1/5), Demo Readiness (1/5)
```

Ask the user: "I found {n} issues. {code_count} are code fixes I can implement,
{data_count} need data changes. Fix all [CODE] and [SPEC] issues automatically?"

If yes, dispatch specialists. If no, report and stop.

**Step 3: Rerun**
1. Rerun ONLY scenes that scored ≤ 3 on any dimension
2. Compare scores against previous run
3. If all scenes 4+/5 → generate deck, declare ship-ready
4. If still ≤ 3 after 3 iterations → report what's left, ask user

**Step 4: Learn**
After the cycle completes (success or user-stopped):
1. Save any new project-specific notes to memory
2. Update scoring calibration if user overrode any scores
3. Record specialist results for future reference

#### Adversarial Mode

Used AFTER a walkthrough passes at 4+/5.

**Step 1:** Invoke walkthrough skill. Verify all scenes 4+/5. If not, suggest
`improve` mode instead.

**Step 2:** Dispatch two parallel adversarial passes via Agent tool:

- **Pass 1 — Code adversarial:** Subagent reviews codebase with adversarial framing.
  Prompt: "This product passes a demo at 4+/5. Find the most embarrassing thing
  a stakeholder would notice. Check AI content generators, data models, edge cases."

- **Pass 2 — Live site adversarial:** Invoke `/qa` in Exhaustive tier. Clicks
  everything, fills forms with edge-case inputs, checks empty states, tests
  responsive viewports.

**Step 3:** For each finding:
1. Verify it's real (subagents may hallucinate)
2. If real, add as new scene in spec OR fix code
3. Rerun expanded walkthrough

**Step 4:** Report findings, update memory with patterns.

#### Eval Framework

New capability modeled on the website-builder eval pattern.

**Commands:**

| Command | Action |
|---------|--------|
| `eval <name>` | Run + score + compare to baseline |
| `eval <name> --update-baseline` | Set current run as new baseline |
| `eval <name> --history` | Show score trends over time |
| `eval <name> --compare <r1> <r2>` | Side-by-side comparison |

**Storage:**

```
screenshots/walkthroughs/<name>/
├── eval-history.json            — array of {date, version, composite, dimensions}
├── baseline.json                — scores from the baseline run
└── runs/
    └── YYYY-MM-DD-vNNN/
        ├── scores.json          — all 5 dimensions per scene + composite
        ├── run-data.json        — full JSON sidecar
        ├── deck.html            — generated presentation
        └── screenshots/         — all scene captures
```

**Composite score:** The composite is the average of all scenes' overall scores
(where each scene's overall = lowest of its 5 dimensions). This single number
enables trend tracking.

**Eval workflow:**
1. Invoke walkthrough skill to run the spec (no user interaction)
2. Save all artifacts to `runs/YYYY-MM-DD-vNNN/`
3. Write `scores.json` with per-scene and composite scores
4. Compare against `baseline.json` if it exists
5. Append to `eval-history.json`
6. Report: composite score, delta from baseline, per-dimension breakdown

### Command (Router)

The command file becomes a thin router. It reads the mode from arguments and
dispatches to either the skill or the agent.

**For skill modes** (`run`, `generate`, no args): Read the walkthrough SKILL.md
from the installed plugin path and follow it.

**For agent modes** (`improve`, `adversarial`, `eval`): The command's frontmatter
already allows the Agent tool. The command dispatches by telling the LLM to follow
the agent's instructions — the agent definition is loaded via the plugin system's
agent mechanism.

## Data Flow

```
User: /walkthrough improve baobab-demo
  │
  ▼
Command (router)
  │ mode = "improve" → agent
  ▼
Agent: walkthrough
  │ 1. Read memory (~/.claude/agent-memory/walkthrough/)
  │ 2. Check project notes for "baobab-demo"
  │
  ▼
Agent invokes Skill: /walkthrough baobab-demo
  │ 1. Setup (browse, state file, dirs)
  │ 2. Auth
  │ 3. Pre-flight
  │ 4. Execute all scenes (screenshot + score)
  │ 5. Generate deck + verify
  │ 6. Write JSON sidecar
  │
  ▼
Agent reads JSON sidecar
  │ Analyze: Scene 4 Content=2, Scene 1 Content=1
  │
  ▼
Agent dispatches specialists
  │ /review for Content failures
  │ /design-review for App Page failures
  │ /qa for Demo Readiness failures
  │
  ▼
Agent invokes Skill: /walkthrough baobab-demo (selective rerun)
  │ Rerun scenes 1, 4 only
  │
  ▼
Agent checks convergence
  │ All 4+/5? → generate deck, save memory
  │ Still failing? → iterate or ask user
```

## Migration

The split is additive — no existing behavior changes for `/walkthrough <name>`,
which still routes directly to the skill. The `improve` and `adversarial` modes
gain the agent wrapper, persistent memory, and eval tracking.

### Changes Required

1. **Trim SKILL.md** — Remove improve mode (lines 523-585), adversarial mode
   (lines 587-630), iteration loop (lines 499-520), and prioritized action list
   (lines 341-371). Update the modes section to list only `run` and `generate`.

2. **Create `agents/walkthrough.md`** — Agent definition with memory, improve
   mode, adversarial mode, eval framework.

3. **Update `commands/walkthrough.md`** — Add routing logic for agent modes.
   Update argument-hint to include `eval`.

4. **Create eval directory structure** — On first eval run (no pre-creation needed).

5. **Bump plugin version** — Patch bump in plugin.json and VERSION.
