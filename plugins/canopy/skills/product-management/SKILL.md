---
name: product-management
description: Use when acting as a product manager for autonomous development — exploring a codebase, proposing improvements, implementing, and learning from outcomes. Invoked by open claws or humans who want structured PM-style development cycles.
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
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

## Two modes

This skill has two operating modes. The phases below describe the **human-gated** mode in detail — that is the original and default behavior.

- **Human-gated** (the Phase 0–6 procedure below). Entry point: `/canopy:pm-scout`. Phase 3 stops on `AskUserQuestion` for per-proposal disposition. Single sprint, exits when dispositions are recorded. **Unchanged.**
- **Autonomous.** Entry points: `/canopy:pm-autonomous` (one sprint) and `/canopy:pm-autonomous-loop` (sprint → wait → repeat). Auto-approves its own proposals. Runs a multi-layer convince-self-it's-clean gate, auto-merges on green CI, auto-deploys, and ends each sprint by sending a working-backwards release-notes email. Requires `$CANOPY_PM_DIR/autonomous.yaml`. See **Autonomous mode** below.

When in doubt, the human-gated mode is the right default. Autonomous mode is opt-in per project via the config file.

## Project State Convention

All project-level PM state lives in `~/.canopy/pm/<project>/` on the user's machine, **not** inside the project tree. The `<project>` part is derived from the project's `origin` remote URL (e.g. `ace-web` from `https://github.com/jjackson/ace-web.git`), falling back to the parent dir of `git-common-dir` when there's no origin. Crucially, this is NOT `basename "$(git rev-parse --show-toplevel)"` — that resolves to the *worktree's* directory name (e.g. `pm-8u5y3` in an emdash worktree), not the project name. Resolve via the snippet under "Resolving the path" below; never hand-roll basename of the toplevel.

```
~/.canopy/pm/<project>/
├── context.md          ← what this project is, who uses it, what matters
├── learnings.md        ← project-specific learnings ("don't propose X again")
├── autonomous.yaml     ← autonomous-mode config (auto-bootstrapped on first run)
└── runs/               ← cycle logs (one per run)
    └── YYYY-MM-DD-<lens>.md
```

**Why this location (not `.claude/pm/` in the project tree):** `.claude/pm/` dies whenever the user works in an emdash or conductor worktree — those worktrees are ephemeral and don't carry the PM state forward. `~/.canopy/pm/<project>/` is per-machine and outlives any worktree.

**Resolving the path** — resolve once at the start of each run and export it:

```bash
CANOPY_PM_PROJECT=$(git config --get remote.origin.url 2>/dev/null | sed 's|.*[/:]||;s|\.git$||')
[ -z "$CANOPY_PM_PROJECT" ] && CANOPY_PM_PROJECT=$(basename "$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)")")
CANOPY_PM_DIR="$HOME/.canopy/pm/$CANOPY_PM_PROJECT"
mkdir -p "$CANOPY_PM_DIR"
```

**Legacy migration:** if a project still has a `.claude/pm/` directory from a previous canopy version, the user should migrate it once:

```bash
CANOPY_PM_PROJECT=$(git config --get remote.origin.url 2>/dev/null | sed 's|.*[/:]||;s|\.git$||')
[ -z "$CANOPY_PM_PROJECT" ] && CANOPY_PM_PROJECT=$(basename "$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)")")
CANOPY_PM_DIR="$HOME/.canopy/pm/$CANOPY_PM_PROJECT"
mkdir -p "$CANOPY_PM_DIR" && mv .claude/pm/* "$CANOPY_PM_DIR/"
```

The skill does NOT auto-migrate — that is user-judgment territory.

**Every run:** Read `context.md` and `learnings.md` before doing anything else. These are your memory.

## Bootstrapping: Building context.md

If `$CANOPY_PM_DIR/context.md` doesn't exist, build it interactively before doing anything else.

**Run all bootstrap steps sequentially.** Do not issue parallel tool calls during bootstrap — `$CANOPY_PM_DIR` may not exist yet, so any parallel call that touches it will fail and cancel its siblings.

### Step 1: Gather what you can automatically

Read these silently (don't dump them to the user). Issue them as **sequential** Read/Bash calls, not parallel:
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

Also create `learnings.md`. If `$CANOPY_PM_DIR/runs/` already exists with previous run logs, parse them for any closed/rejected items and pre-populate the "Closed Items" section. Otherwise start empty:

```markdown
# Product Management Learnings

Items closed or rejected during PM cycles. Read this before every scout run to avoid re-proposing.

## Closed Items
(none yet)

## Preferences
(none yet)
```

## The Loop

### Phase 0: Pre-flight (single sequential check, NEVER parallel)

**Run this ONE bash command synchronously before any other tool calls.** Do not parallelize anything until this completes — issuing parallel reads when the directory doesn't exist cancels every sibling call and forces sequential retries.

```bash
CANOPY_PM_PROJECT=$(git config --get remote.origin.url 2>/dev/null | sed 's|.*[/:]||;s|\.git$||')
[ -z "$CANOPY_PM_PROJECT" ] && CANOPY_PM_PROJECT=$(basename "$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)")")
CANOPY_PM_DIR="$HOME/.canopy/pm/$CANOPY_PM_PROJECT"
mkdir -p "$CANOPY_PM_DIR"
[ -f "$CANOPY_PM_DIR/context.md" ] && echo "PM_STATE: ready" || echo "PM_STATE: missing"
```

Branch on the output:

- **`PM_STATE: missing`** → Run the **Bootstrap** flow (see "Bootstrapping: Building context.md" above) **synchronously**. Do not issue parallel reads. After bootstrap completes, proceed to Phase 1.
- **`PM_STATE: ready`** → Proceed directly to Phase 1.

### Phase 1: Scout (explore, read-only)

**What to do:**
1. Read `$CANOPY_PM_DIR/context.md` for orientation
2. Read `$CANOPY_PM_DIR/learnings.md` for things to avoid
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
- Check `$CANOPY_PM_DIR/learnings.md` — do NOT re-propose closed or rejected items.

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
- **Review backlog**: Parse all previous run logs in `$CANOPY_PM_DIR/runs/` and collect items marked as "Backlog". Present each backlogged item via `AskUserQuestion` with options: **Promote** (move to "Do it" this cycle), **Keep** (leave in backlog), **Close** (won't do, log reason). This prevents the backlog from becoming a graveyard of forgotten ideas.

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

Write run log to `$CANOPY_PM_DIR/runs/YYYY-MM-DD-<lens>.md`:

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

Update `$CANOPY_PM_DIR/learnings.md` with any new closed items or preferences.

**2. Evaluate for universal improvements** (see Self-Improvement Protocol below).

## Autonomous mode

The procedure for autonomous sprints lives in template files. Read them in order at the start of every autonomous run:

1. `templates/autonomous/config-schema.md` — `$CANOPY_PM_DIR/autonomous.yaml` schema and example
2. `templates/autonomous/cycle.md` — Phases A–E (the working-backwards sprint)
3. `templates/autonomous/convince-self-gate.md` — the multi-layer gate that runs before every PR
4. `templates/autonomous/email-format.md` — body template for the working-backwards release-notes email

These templates are read using the Read tool from the cached plugin path:

```bash
PLUGIN_PATH=$(python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'])")
ls "$PLUGIN_PATH/skills/product-management/templates/autonomous/"
```

The autonomous mode does NOT modify the human-gated Phase 0–6 procedure above. `/canopy:pm-scout` still runs the human-gated path verbatim.

### Hard rules for autonomous mode

1. **No proposal advances without passing the convince-self gate.** Mechanical checks, five self-review questions, dogfood (when applicable), post-deploy health.
2. **No weak emails.** Phase A loops until the email draft passes Clear/Testable/Impressive. Phase D refuses to send if reality diverged into something not worth sending — it sends a stuck-state note instead.
3. **Emails ship as HTML with prod screenshots, clickable feature elements, and a render-and-look pass before AND after send.** The release-notes email is the only customer-facing output of the cycle — visual quality matters and is part of user delight. The hard contract: body must be HTML (sender skill's `--body-html` or equivalent), screenshots must come from prod (not localhost), inline images must use persistent https URLs (e.g. `raw.githubusercontent.com` against a `pm-assets/<sprint-slug>` branch on the project's repo — `cid:` and data URIs don't render reliably in Gmail), every highlight's title AND hero image must wrap in `<a href="<TRY-IT-URL>">` so recipients can click anywhere intuitive, AND the cycle MUST render the final `email.html` in a real browser at desktop + mobile widths before sending (E.4 gate) and again after sending to write a self-critique with concrete improvement ideas (E.5). See `templates/autonomous/email-format.md` "Hard rules" + reference layout + "Self-review" section.
4. **One autonomous PR in flight at a time.** Resume an open one before opening a new one.
5. **No auto-revert on broken prod.** Fix forward, up to `guardrails.max_fix_forward_attempts` cycles, then stop with a stuck-state email.
6. **The skill stays project-agnostic.** Every project-specific value (deploy command, health URLs, sender skill, branch prefix, test commands) lives in `~/.canopy/pm/<project>/autonomous.yaml`. Never hardcode them in SKILL.md or templates.

## Self-Improvement Protocol

After completing a cycle, evaluate your meta-observations:

### Is this learning project-specific?
Examples: "don't propose keyboard shortcuts for this project", "this repo uses pytest not jest"

→ Write to `$CANOPY_PM_DIR/learnings.md`. Done.

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
9. **For adoption-blockers scouts, diff the template against BOTH the installed copy AND the code tree.** When a project ships a template file (`.env.tpl`, `config.example.yml`, `settings.template.json`, etc.) that the user instantiates into a live copy, adoption-blockers come in two subclasses and you need two diffs to surface both:
   - **Forward diff** — `diff <(keys from installed copy) <(keys from template)`. Catches keys added to the template after the user last instantiated. Classic drift: new release adds a var, existing installs don't auto-pick it up, feature silently breaks.
   - **Inverse sweep** — for each key in the template, `grep -rE "\b$KEY\b"` across the code-bearing dirs (source/, lib/, scripts/, skills/, bin/, hooks/, etc.). Catches keys declared but never read — dead ceremony that the user pastes / injects / configures for no runtime benefit.
   Forward-only scouts miss the second class entirely; most first-run friction lives there (paste-this lines in READMEs for values nothing consumes). Both diffs are one-line commands; run them together in Phase 1 Step 1 of every adoption-blockers scout and carry any hits from either into proposals. Bonus: either class closes nicely with a class-level doctor/health-check (same pattern as any bottleneck pre-flight).
10. **Before shipping a diagnostic check, exercise it against both PASS and FAIL inputs.** When adding a doctor/health-check/CI gate that emits PASS/WARN/FAIL, run it against a known-good state AND a synthetic bad state at authoring time — confirm it passes when it should and fires when it should. Two failure modes to catch:
    - **Check itself is wrong (false positives).** A grep filter that over-excludes, a regex that's too narrow, a comparison against the wrong field. Ships a green check that misses the real problem, or (worse) a noisy check that users learn to ignore.
    - **Remediation hint is unreachable (false fixes).** The `fix:` command the check tells the user to run might not actually work — a command-line flag that doesn't parse, a reference that errors out. Test the hint end-to-end at least once before landing.
    Common pitfall: the check author has a mental model that's out of sync with what the check is actually doing (regex, filter, or path). The mental model says "this will catch X"; the code says "this will catch X minus some edge case Y." Running against a known-good input with a known-good result surfaces the gap before users do. Applies to any diagnostic — doctor scripts, lint rules, CI assertions, test preconditions.
11. **The release-notes email is the only customer-facing output of the autonomous cycle — its visual quality matters.** Five rules surfaced in real use, captured in detail in `templates/autonomous/email-format.md`:
    - **HTML body, never raw markdown.** Mail clients render HTML; markdown handed in renders as literal `##`/`**`/`-` characters and looks amateur. The sender skill must be invoked with `--body-html` (or equivalent) and a brief plain-text fallback for `--body`.
    - **Screenshots from prod, never localhost.** Drive the deployed app via the configured `headless_browser_skill` and authenticate via the project's automation login (e.g. `/auth/e2e-login/`). Localhost shots show port numbers and seeded fake data — recipients spot it and lose trust.
    - **Inline images via persistent https URLs, never `cid:` and never data URIs.** Most CLI mailers (e.g. `gog gmail send`) emit `multipart/mixed` when given attachments, so `cid:` refs in the HTML resolve to broken-image icons. Data URIs are stripped by many clients. Reliable pattern: commit the screenshots to a `pm-assets/<sprint-slug>` branch on the **project's** origin (not canopy's) and reference via `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>` in the `<img src>`.
    - **Every feature highlight is clickable in three places — title, hero image, AND the explicit "Try it" CTA.** A small CTA buried at the bottom of each card is not enough; recipients scan and shouldn't have to hunt for the click target. Wrap each highlight's `<h2>` and `<img>` in `<a href="<TRY-IT-URL>">` (with `text-decoration:none`).
    - **Render-and-look passes BEFORE and AFTER sending.** Phase E.4 (pre-send gate) renders `email.html` via the configured `headless_browser_skill` at desktop + mobile widths and refuses to send if anything looks off. Phase E.5 (post-send critique) writes a self-review into the run log with 2-4 concrete improvement ideas surfaced as the cycle's closing message to the user. Without these passes, visual-quality drift goes unnoticed across cycles.

    Visual design: typographic hierarchy over bordered boxes, restrained palette, hero image per highlight, footer for internal notes — see the canonical layout in `email-format.md`. Reference standard is "Linear / Stripe / Vercel changelog", not "GitHub issue body". Surfaced 2026-04-29 from real PM feedback after the first autonomous run on ace-web.

## Token Efficiency

- **Scout phase**: one call, focused by lens
- **Implement phase**: one call per task, scoped tightly with acceptance criteria
- **Don't explore everything every run**: use one lens, rotate across runs
- **Read context.md and learnings.md upfront** — don't re-discover what's already known
