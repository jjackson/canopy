---
name: product-management
description: Use when acting as a product manager for autonomous development — exploring a codebase, proposing improvements, implementing, and learning from outcomes. Invoked by open claws or humans who want structured PM-style development cycles.
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
[ -n "$_CANOPY_UPD" ] && echo "$_CANOPY_UPD"
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# Product Management — Autonomous Product Development

## Purpose

Act as PM + engineer for the current project: explore the codebase, propose improvements, implement approved changes, and learn from outcomes. The meta-goal is **getting better at getting better** — improving this process itself over time.

## Architecture

```
Supervisor (manager)                Claude Code (PM/engineer)
─────────────────                   ────────────────────────
Sets priorities & context     →     Explores codebase (read-only first)
Filters & ranks proposals     ←     Proposes improvements with rationale
Approves / redirects          →     Implements on branch + tests
Validates & reports           ←     Reports results
Logs outcomes & learns
```

### Why This Structure
- **Supervisor stays responsive** — never blocked by long Claude runs
- **Claude gets focused context** — one project, one task, clear acceptance criteria
- **Learning accumulates** in files that persist across sessions

## Project State Convention

All project-level data lives in `.claude/pm/` within the current project:

```
<project-root>/
└── .claude/
    └── pm/
        ├── context.md          ← what this project is, who uses it, what matters
        ├── learnings.md        ← project-specific learnings ("don't propose X again")
        └── runs/               ← cycle logs (one per run)
            └── YYYY-MM-DD-<lens>.md
```

**Every run:** Read `context.md` and `learnings.md` before doing anything else. These are your memory.

## Bootstrapping: Building context.md

If `.claude/pm/context.md` doesn't exist, build it interactively before doing anything else.

### Step 1: Gather what you can automatically

Read these silently (don't dump them to the user):
- `CLAUDE.md` and `README.md` for project identity
- `package.json`, `pyproject.toml`, or equivalent for tech stack
- `git log --oneline -10` for recent activity
- Directory structure (top 2 levels) for shape of the codebase

### Step 2: Ask the user focused questions

Ask these **one at a time**, using what you learned in Step 1 to make them specific:

1. **"What does this project do in one sentence?"** — You'll have a guess from the README. Offer it and ask them to correct or confirm. Don't ask if the README already says it clearly.

2. **"Who uses this and how?"** — Ask about the actual users and their workflow. This is the most important question. Push for specifics: job role, how often, what they're trying to accomplish. Don't accept vague answers like "developers" — ask "what kind of developers, doing what?"

3. **"What matters most for this product right now?"** — Give 2-3 options based on what you've seen (e.g., "reliability for existing users" vs "new features to drive adoption" vs "reducing technical debt to move faster"). Let them pick or reframe.

4. **"Anything I should know about how this project works that isn't obvious from the code?"** — Open-ended. Captures tribal knowledge: deployment quirks, known gotchas, political constraints, integration dependencies.

Skip any question where the answer is already clear from the code. Don't ask 4 questions if 2 will do.

### Step 3: Write context.md

Write a short, dense file. Target: **under 40 lines**. Use this structure:

```markdown
# <Project Name> — Product Context

## What It Is
One sentence.

## Who Uses It
- **Primary users**: role, frequency, what they're trying to do
- **Usage pattern**: how they actually interact with it (ad-hoc, batch, continuous, etc.)

## What Matters Most
Numbered list, max 3 items. Each one sentence.

## Tech Stack
Bullet list of key technologies. Only what's relevant to making good proposals.

## Current State
2-3 sentences: what's working, what's active, what's rough.

## Known Considerations
Bullet list of non-obvious things: gotchas, constraints, political context, integration dependencies.
```

### Step 4: Confirm

Show the user the generated `context.md` and ask: "Does this capture your project accurately? Anything to add or fix?" Edit based on their feedback, then save.

Also create `learnings.md`. If `.claude/pm/runs/` already exists with previous run logs, parse them for any closed/rejected items and pre-populate the "Closed Items" section. Otherwise start empty:

```markdown
# Product Management Learnings

Items closed or rejected during PM cycles. Read this before every scout run to avoid re-proposing.

## Closed Items
(none yet)

## Preferences
(none yet)
```

## The Loop

### Phase 1: Scout (explore, read-only)

**What to do:**
1. Read `.claude/pm/context.md` for orientation
2. Read `.claude/pm/learnings.md` for things to avoid
3. Check `git log --oneline -20` for recent momentum
4. Run the test suite — what passes, fails, is missing?
5. Look through open issues / TODO files
6. Explore through a specific lens (see below)

**Exploration Lenses** (use one per run, rotate):
- **User value**: what features would users love? What workflows are clunky?
- **Adoption blockers**: what makes someone stop using this? First-run friction, confusing UX, unreliable behavior
- **Integration depth**: how well does this connect to its ecosystem? Deeper = stickier
- **Trust & reliability**: bugs, wrong answers, silent failures, missing error handling
- **Tech debt**: dead code, flaky tests, missing types, outdated deps

**Output format:**
For each finding, provide:
- **Title**: one line
- **What**: specific files/functions affected
- **Why it matters**: impact on users or developers
- **Effort**: S (< 1hr) / M (2-4hr) / L (day+)
- **How to validate**: concrete test or check that proves it's fixed
- **Risk**: what could go wrong

**Critical rules:**
- Check what already exists before proposing additions. Verify current state.
- Don't suggest vague refactors or "add more tests everywhere." Be specific.
- For bugs or broken behavior: try to write a failing test. If you can't, explain why.
- Check `.claude/pm/learnings.md` — do NOT re-propose closed or rejected items.

### Phase 2: Propose (supervisor filters & ranks)

Supervisor reviews findings and:
1. Filters out low-value or risky items
2. Ranks by: user impact x feasibility x alignment with priorities
3. Picks top 3 to present

**Presentation format:**
> **Title** (Effort: S/M/L)
> What: one sentence
> Why: one sentence on impact
> Validate: how we'll know it works

### Phase 3: Approve (interactive menu)

Present proposals using `AskUserQuestion` so the user can give per-item dispositions through a structured menu rather than free-form chat. Each proposal gets its own question with four options:

- **Do it** → move to implement now
- **Backlog** → good idea, not now
- **Close** → don't want this, log the reason
- **Redirect** → re-scope it

Use `AskUserQuestion` with up to 4 questions (one per proposal). Each question should include the proposal title, effort, what/why/validate summary in the question text, and use `header` for a short label (e.g. "Skill Transfer"). The four disposition options above are the choices. The user can also select "Other" to provide custom feedback.

Example:
```
AskUserQuestion({
  questions: [
    {
      question: "Proposal 1: Add transfer-skill command (Effort: M)\n\nWhat: ...\nWhy: ...\nValidate: ...\n\nWhat's your disposition?",
      header: "Skill Transfer",
      options: [
        { label: "Do it", description: "Implement this now" },
        { label: "Backlog", description: "Good idea, not now" },
        { label: "Close", description: "Don't want this, won't revisit" },
        { label: "Redirect", description: "Re-scope — I have specific feedback" }
      ],
      multiSelect: false
    },
    // ... one question per proposal, up to 4
  ]
})
```

Track all dispositions in the run log. Closed items go into `learnings.md` so they're never proposed again.

**After dispositions**, ask the user what they'd like to do next:

```
AskUserQuestion({
  questions: [{
    question: "Anything else before we move on?",
    header: "Next step",
    options: [
      { label: "Move on", description: "Proceed to implementation / learning" },
      { label: "Add my own ideas", description: "I have ideas to add to this cycle" },
      { label: "Review backlog", description: "See backlogged items from previous runs — promote or close them" }
    ],
    multiSelect: false
  }]
})
```

- **Add my own ideas**: Capture the user's ideas and apply the same disposition flow (Do it / Backlog / Close). Log user-originated ideas in the run log with a `[user idea]` tag.
- **Review backlog**: Parse all previous run logs in `.claude/pm/runs/` and collect items marked as "Backlog". Present each backlogged item via `AskUserQuestion` with options: **Promote** (move to "Do it" this cycle), **Keep** (leave in backlog), **Close** (won't do, log reason). This prevents the backlog from becoming a graveyard of forgotten ideas.

This keeps the scout session self-contained — the user doesn't need to break out of the cycle to contribute thoughts or revisit past decisions.

### Phase 4: Implement

**Key principles:**
- Give Claude a way to verify its work — always include test commands or expected output
- Always branch + PR: `<prefix>/<short-slug>`, never commit to main
- Claude must run full validation (lint + build + tests) and report output
- Commit with clear message, push and create PR

**Implementation prompt includes:**
- What to build (specific files, functions, behavior)
- Acceptance criteria (tests to pass, behavior to verify)
- Constraints (don't change X, follow pattern in Y)
- Verification command

**If validation fails:**
- Fix the issues and re-run validation
- If you can't fix after 2 attempts, report what's failing and stop — don't keep thrashing
- Run `/simplify` after implementation to catch code reuse, quality, and efficiency issues

### Phase 5: Validate & Ship

- Tests pass, build succeeds, no regressions
- Create branch, commit, push, create PR
- If code review bots are active: wait for review, address comments
- Verify CI passes
- Merge via squash

### Phase 6: Learn

After each cycle, do two things:

**1. Update project state:**

Write run log to `.claude/pm/runs/YYYY-MM-DD-<lens>.md`:

```markdown
## YYYY-MM-DD — <lens>

### Do it
1. **Title** — Effort: S — Status: pending/done/merged
   - Branch: prefix/slug
   - Outcome: ...

### Backlog
1. **Title** — Effort: M — Why not now: "..."

### Closed
1. **Title** — Why: "user said..."
   - Learning: don't propose X-type things

### Meta-observations
- What worked well
- What was wasteful
- Prompt adjustments for next time
```

Update `.claude/pm/learnings.md` with any new closed items or preferences.

**2. Evaluate for universal improvements** (see Self-Improvement Protocol below).

## Self-Improvement Protocol

After completing a cycle, evaluate your meta-observations:

### Is this learning project-specific?
Examples: "don't propose keyboard shortcuts for this project", "this repo uses pytest not jest"

→ Write to `.claude/pm/learnings.md`. Done.

### Is this learning universal?
Examples: "Claude over-engineers when not told to check existing functionality", "always verify current state before proposing additions"

→ Propose a PR to `jjackson/canopy` (NOT the current project repo):

1. Clone `jjackson/canopy` to a temp directory (or use an existing clone)
2. Create branch: `learn/<short-description>`
3. Edit: `plugins/canopy/skills/product-management/SKILL.md`
3. Make the specific improvement (new lesson, tightened instruction, revised template)
4. Never delete existing lessons — refine or append
5. Open PR with:
   - **What was learned**: the universal insight
   - **Evidence**: which project/run surfaced it
   - **Change**: before/after of the affected section

The PR will be reviewed before merging. This is intentional — unchecked self-modification can degrade the skill.

## Lessons Learned

1. **Don't assume usage patterns** — ask about how people actually use the product before theorizing. Verify with the user.
2. **Claude over-engineers solutions** — check what already exists before proposing new infrastructure. The field/API/feature may already be there.
3. **Speculation without evidence has low hit rate** — when proposing from code structure alone without testing, expect most proposals to miss. Write failing tests as proof.
4. **Architectural issues: flag, don't fix** — things that need design direction should be logged, not autonomously implemented.
5. **Product value > engineering elegance** — proposals should lead with user impact, not code cleanliness.
6. **Always git pull before exploring** — stale code = stale proposals.
7. **Feed closed items into future runs** — without this, Claude re-proposes rejected ideas. Always read `learnings.md` first.
8. **Use structured menus for dispositions** — presenting proposals via `AskUserQuestion` with per-item options gives the user precise control and avoids ambiguous bulk chat responses. Each proposal should be independently dispositioned.

## Token Efficiency

- **Scout phase**: one call, focused by lens
- **Implement phase**: one call per task, scoped tightly with acceptance criteria
- **Don't explore everything every run**: use one lens, rotate across runs
- **Read context.md and learnings.md upfront** — don't re-discover what's already known
