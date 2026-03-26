# Website Builder Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Canopy plugin agent that generates marketing websites from product context, with an evaluation framework for tracking quality over time.

**Architecture:** A Claude Code agent (`@website-builder`) with persistent memory orchestrates a pipeline of existing skills (/frontend-design, /design-consultation, /browse, /design-review). An eval framework saves inputs + outputs + scores for each generation run, enabling improvement tracking. Connect is the first eval suite.

**Tech Stack:** Claude Code agents (markdown definition + memory: user), Claude Code skills (SKILL.md), existing gstack/CC plugins, Python 3 for local HTTP server during QA, JSON for eval data.

---

## File Structure

### New Files

```
plugins/canopy/agents/website-builder.md          — Agent definition (system prompt + pipeline)
plugins/canopy/skills/website-builder/SKILL.md     — Eval skill (scoring, comparison, history)
plugins/canopy/commands/website-builder.md          — Command wrapper for the skill
evals/connect/context/product-brief.md             — Connect product description (fixed input)
evals/connect/context/brand-guidelines.md          — Dimagi brand rules (fixed input)
evals/connect/context/tone-reference.md            — Connect voice examples (fixed input)
evals/connect/context/reference-sites.md           — Aspirational reference sites (fixed input)
evals/connect/baseline.json                        — Initial empty baseline
evals/connect/eval-history.json                    — Initial empty history
```

### Modified Files

```
plugins/canopy/.claude-plugin/plugin.json          — Bump version (patch)
VERSION                                            — Bump version (match plugin.json)
```

---

### Task 1: Create the Connect Eval Context Fixtures

**Files:**
- Create: `evals/connect/context/product-brief.md`
- Create: `evals/connect/context/brand-guidelines.md`
- Create: `evals/connect/context/tone-reference.md`
- Create: `evals/connect/context/reference-sites.md`
- Create: `evals/connect/baseline.json`
- Create: `evals/connect/eval-history.json`

These are the FIXED inputs that don't change between eval runs. They represent the "test fixture" for the Connect product.

- [ ] **Step 1: Create the eval directory structure**

Run:
```bash
mkdir -p evals/connect/context evals/connect/runs
```

- [ ] **Step 2: Write the Connect product brief**

Create `evals/connect/context/product-brief.md`:

```markdown
# CommCare Connect — Product Brief

## What It Is

CommCare Connect is Dimagi's platform for verified service delivery at the
frontline. It links funding directly to verified outcomes — enabling frontline
workers to learn, deliver services, and get paid through a single digital tool.

## How It Works

1. **Learn** — Workers select and receive training through a digital training
   platform integrated with CommCare.
2. **Deliver** — Workers deliver services via their active jobs, using CommCare
   for data collection and workflow management.
3. **Verify & Pay** — Service delivery is verified using biometrics, GPS, and
   data algorithms. Workers receive fair, transparent compensation managed
   end-to-end on the platform.

## Key Features

- **Verified delivery**: Biometric verification, GPS tracking, and algorithmic
  validation ensure services were actually delivered.
- **Transparent payments**: Full payment cycle visibility — from earnings
  calculation to delivery — accessible to every worker.
- **Worker empowerment**: Community health workers choose whether to opt into
  additional tasks. Flexibility without exploitation.
- **Funding accountability**: Donors and funders see exactly where money goes
  and what outcomes it produces.
- **Built on CommCare**: Leverages the CommCare platform used by 350,000+
  frontline workers in 80+ countries.

## Impact Numbers

- 101,000+ health services delivered
- $10:1 ROI demonstrated by the Financing Alliance for Health
- Based on economic multiplier effect from paying frontline workers

## Target Audience

### Primary: Funders and Development Organizations
- Global health funders wanting accountability for their investments
- NGOs seeking verified impact measurement
- Government health programs needing transparent delivery tracking

### Secondary: Frontline Workers
- Community health workers seeking fair compensation
- Field workers wanting flexible, dignified work through technology

## Core Value Proposition

"More transparency, accountability, and impact." CommCare Connect creates a
new model for global development by linking funding directly to verified
frontline service delivery.

## Competitive Differentiation

- Only platform that integrates training, delivery, verification, AND payment
  in a single tool for frontline workers
- Built on CommCare's proven infrastructure (15+ years, 80+ countries)
- Worker-centric design: workers choose their tasks, see their earnings
- Verification is built-in, not bolted on

## Key Terms (must appear in generated content)

- CommCare Connect
- verified service delivery
- frontline workers
- learn, deliver, verify & pay
- biometric verification
- transparent payments
- funding accountability
- community health workers
```

- [ ] **Step 3: Write the brand guidelines**

Create `evals/connect/context/brand-guidelines.md`:

```markdown
# Dimagi Brand Guidelines (for Website Generation)

## Brand Voice

- **Professional but human**: We work in global health and development —
  serious work, but we talk about it accessibly.
- **Evidence-driven**: Lead with numbers, impact, and proof. Avoid vague claims.
- **Empowering, not paternalistic**: Frontline workers are partners, not
  beneficiaries. Technology enables them; it doesn't save them.
- **Clear over clever**: Straightforward language. No jargon walls. If a
  funder can't understand it in 10 seconds, rewrite it.

## Visual Identity

- **Primary color**: Dimagi Blue (#1D5F8A)
- **Secondary color**: Dimagi Orange (#F7941D)
- **Accent**: White (#FFFFFF), Light Gray (#F5F5F5)
- **Dark text**: #333333
- **Typography**: Clean, modern sans-serif. Prefer system fonts or widely
  available web fonts (e.g., Inter, Source Sans Pro). No decorative fonts.
- **Imagery style**: Real photos of frontline workers in the field, not
  stock photos. When illustrations are used, they should be simple and
  warm, not corporate.

## Layout Principles

- **Mobile-first**: Most users in our market access content on mobile devices.
- **Generous whitespace**: Let the content breathe. No cramped layouts.
- **Clear hierarchy**: One primary CTA per section. Don't compete for attention.
- **Data visualization**: When showing impact numbers, make them large and
  prominent. Numbers are our strongest proof points.

## What to Avoid

- Generic stock photography of "diverse teams in offices"
- Purple/gradient AI aesthetic
- Dense walls of text
- Jargon without explanation (e.g., "digital health ecosystem")
- Claims without evidence
```

- [ ] **Step 4: Write the tone reference**

Create `evals/connect/context/tone-reference.md`:

```markdown
# Connect Tone Reference

## Examples of Good Connect Copy

### Hero-level messaging
"Funding meets the frontline. CommCare Connect links every dollar to verified
service delivery — so funders see impact, and workers get paid."

### Feature description
"Workers choose which tasks to take on, complete training at their own pace,
and see exactly what they've earned. Every service is verified through
biometrics and GPS before payment is released."

### Impact statement
"101,000+ health services delivered. $10 returned for every $1 invested.
That's the economic multiplier when you pay frontline workers fairly."

### CTA
"See how CommCare Connect is changing the model for global development."

## Tone Calibration

- Formal/Casual: 6/10 (professional but approachable)
- Technical/Accessible: 4/10 (accessible to funders, not engineers)
- Urgent/Measured: 5/10 (important work, but not alarmist)

## Words We Use

- "frontline workers" (not "beneficiaries" or "end users")
- "verified" (not "tracked" or "monitored")
- "funding accountability" (not "donor oversight")
- "fair compensation" (not "incentives" or "stipends")

## Words We Avoid

- "disrupting" (overused, meaningless)
- "leveraging" (corporate jargon)
- "empowerment" without concrete examples of what that means
- "scalable solution" (show the scale instead)
```

- [ ] **Step 5: Write the reference sites**

Create `evals/connect/context/reference-sites.md`:

```markdown
# Reference Sites

Sites whose design quality and approach we admire. These inform the
aesthetic direction, not the content.

## Direct Competitors / Adjacent
- https://dimagi.com — Parent company. WordPress. Good content, dated design.
- https://ona.io — Data platform for global development. Clean, modern.
- https://www.medic.org — Community health toolkit. Warm, human-centered.

## Design Inspiration (non-competitor)
- https://stripe.com — Gold standard for product marketing pages. Clear
  hierarchy, great use of whitespace, strong CTAs.
- https://linear.app — Modern SaaS marketing. Bold typography, minimal.
- https://vercel.com — Developer-focused but beautiful information hierarchy.

## What We Like About These
- Clear information hierarchy (most important thing visible in 2 seconds)
- Real screenshots / product visuals (not abstract illustrations)
- Impact numbers displayed prominently
- Single CTA per viewport
- Mobile-first responsive design
- Fast loading, minimal JavaScript
```

- [ ] **Step 6: Create initial eval data files**

Create `evals/connect/baseline.json`:

```json
{
  "run_id": null,
  "overall": 0,
  "dimensions": {},
  "note": "No baseline set yet. Run @website-builder eval connect --update-baseline after first satisfactory run."
}
```

Create `evals/connect/eval-history.json`:

```json
{
  "product": "connect",
  "runs": []
}
```

- [ ] **Step 7: Commit the eval fixtures**

```bash
git add evals/
git commit -m "feat: add Connect eval context fixtures for website builder

Fixed test inputs for the evaluation framework: product brief,
brand guidelines, tone reference, and reference sites. These
don't change between eval runs — they measure agent quality.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Create the Website Builder Agent Definition

**Files:**
- Create: `plugins/canopy/agents/website-builder.md`

This is the core agent — its system prompt defines the entire pipeline.

- [ ] **Step 1: Write the agent definition**

Create `plugins/canopy/agents/website-builder.md`:

```markdown
---
name: website-builder
description: >
  Build polished marketing websites from product context. Reads brand guidelines
  from persistent memory and product collateral from ./context/, orchestrates
  design and generation skills, QAs the output, and iterates based on feedback.
  Also runs evaluation suites to track quality over time.
model: inherit
memory: user
---

# Website Builder Agent

You are a website builder agent. Your job is to create polished, deployable
marketing websites from product context, and to evaluate and improve your own
output quality over time.

## Your Memory

Your persistent memory at `~/.claude/agent-memory/website-builder/` stores
Dimagi-wide brand context that applies to ALL products:
- Brand guidelines (visual identity, colors, typography)
- Tone of voice (writing style, words to use/avoid)
- Approved aesthetics (design choices the user has approved in past sessions)

Read your MEMORY.md first. If it's empty, that's fine — you'll build it up
over time as the user approves designs and gives feedback.

## Product Context

Product-specific context lives in the working directory:

```
./context/
├── product-brief.md       — What the product does, features, audience
├── value-propositions.md  — Key messaging hierarchy
├── target-audience.md     — Who we're talking to
└── reference-materials/   — 2-pagers, decks, supporting docs
```

If `./context/` doesn't exist, tell the user:
"No product context found. Create a `context/` directory with at least a
`product-brief.md` describing the product."

## Commands

### `generate` (default)

Run the full generation pipeline:

**Stage 1: Context Ingestion**
1. Read all files in `./context/`
2. Read your agent memory for brand guidelines
3. Synthesize into a **creative brief** — a single markdown document that
   contains: product name, value proposition, target audience, key features,
   tone profile, brand constraints, and design direction.
4. Print a summary: "Creative brief ready. Product: {name}. Audience: {audience}.
   Tone: {tone}. Generating..."

**Stage 2: Design System**
1. Check if `DESIGN.md` exists in the working directory.
2. If yes, read it and use it.
3. If no, use the Skill tool to invoke `/design-consultation` with the creative
   brief as context. This produces a DESIGN.md.
4. If `/design-consultation` fails, create a minimal DESIGN.md from the brand
   guidelines in your memory.

**Stage 3: Generation**
1. Use the Skill tool to invoke `/frontend-design` with this prompt structure:

   "Build a marketing landing page for {product_name}.

   CREATIVE BRIEF:
   {creative_brief_content}

   DESIGN SYSTEM:
   {design_md_content}

   REQUIREMENTS:
   - Single-page marketing landing page
   - Self-contained HTML/CSS/JS (no external dependencies except Google Fonts)
   - Sections: Hero, Key Features (3-4), How It Works, Impact/Social Proof, CTA
   - Mobile-first responsive design
   - Output files to ./output/ directory"

2. If generation fails, retry once with a simplified prompt (remove DESIGN
   SYSTEM section). If it fails again, report the error.

**Stage 4: QA**
1. Start a local HTTP server:
   ```
   python3 -m http.server 0 --directory ./output/
   ```
   Parse the actual port from the output.

2. Use the Skill tool to invoke `/browse` commands:
   - `goto http://localhost:{port}`
   - `screenshot ./screenshots/desktop.png` (default viewport)

3. Read the screenshot to visually verify the page looks correct.

4. Kill the HTTP server.

5. If screenshot capture fails, skip visual QA and tell the user:
   "Could not capture screenshots. Please open ./output/index.html directly."

**Stage 5: User Review**
Present the screenshot to the user and ask:
"Here's the generated page. What would you like to do?"
- **Approve** — Save to output, optionally update memory with preferences
- **Revise** — Tell me what to change (e.g., "hero needs more urgency",
  "wrong color palette"). I'll regenerate.
- **Regenerate** — Start fresh with a different approach.

**Stage 6: Iteration**
If the user wants revisions:
1. Note what they want changed
2. Store the feedback
3. Re-run Stage 3 with the feedback appended to the prompt
4. Re-run Stages 4-5
5. Maximum 5 iteration cycles. After 5, tell the user:
   "Reached iteration limit. Here's the current output. You can approve it
   or start a new generation session."

On approval:
1. Save any aesthetic preferences to your agent memory
   (e.g., "User prefers bold typography", "User approved blue/orange palette")
2. Tell the user: "Page approved! Files are in ./output/. Deploy to any
   static hosting provider."

### `eval <product>`

Run the evaluation framework. See the `website-builder` skill for the full
eval workflow. In short:

1. Read fixed context from `evals/<product>/context/`
2. Copy context to a temp `./context/` directory
3. Run the full generation pipeline (stages 1-4, no user review)
4. Save outputs to `evals/<product>/runs/YYYY-MM-DD-vNNN/`
5. Score each dimension (visual, brand, content, responsive, code)
6. Compare against baseline
7. Report results

### `eval <product> --update-baseline`

Set the most recent run as the new baseline for comparison.

### `eval <product> --history`

Show score trends over time from `evals/<product>/eval-history.json`.

### `eval <product> --compare <run1> <run2>`

Side-by-side comparison of two runs.

## Rules

- Output goes to `./output/` directory (static HTML/CSS/JS only)
- Max 5 iteration cycles before forcing user review
- Never generate generic AI marketing copy — every claim must trace to product
  context. If the context doesn't mention a feature, don't invent it.
- Store approved aesthetic preferences in memory for future sessions
- When the user gives feedback, quote it back in the next prompt so /frontend-design
  knows exactly what to change
```

- [ ] **Step 2: Commit the agent**

```bash
git add plugins/canopy/agents/website-builder.md
git commit -m "feat: add website-builder agent definition

Agent with persistent memory (memory: user) that orchestrates a pipeline
of /design-consultation, /frontend-design, /browse for generating marketing
websites from product context. Supports generate and eval commands.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Create the Website Builder Eval Skill

**Files:**
- Create: `plugins/canopy/skills/website-builder/SKILL.md`

The skill handles evaluation-specific logic: scoring, comparison, history tracking.

- [ ] **Step 1: Write the eval skill**

Create `plugins/canopy/skills/website-builder/SKILL.md`:

````markdown
---
name: website-builder
description: |
  Evaluation framework for the website builder agent. Scores generated websites
  on 5 dimensions (visual quality, brand consistency, content accuracy,
  responsiveness, code quality), tracks scores over time, and enables A/B
  comparison between runs. Use when asked to "eval", "score", or "compare"
  website builder output.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
---

# Website Builder Evaluation

## Eval Workflow

When the agent invokes `eval <product>`:

### Step 1: Setup

```bash
PRODUCT="$1"
EVAL_DIR="evals/$PRODUCT"
CONTEXT_DIR="$EVAL_DIR/context"
```

1. Verify `$EVAL_DIR/context/` exists and has files.
2. Determine run ID: check `$EVAL_DIR/runs/` for existing runs today,
   increment version number. Format: `YYYY-MM-DD-vNNN` (e.g., `2026-03-25-v001`).
3. Create run directory: `$EVAL_DIR/runs/$RUN_ID/`

### Step 2: Generate

1. Create a temporary working directory with the eval context:
   ```bash
   WORK_DIR=$(mktemp -d /tmp/website-builder-eval-XXXXXXXX)
   cp -r $CONTEXT_DIR $WORK_DIR/context
   mkdir -p $WORK_DIR/output $WORK_DIR/screenshots
   ```

2. Run the generation pipeline by reading context files and invoking
   /frontend-design. Follow the same pipeline as the agent's `generate`
   command, but skip user review (Stage 5) — eval runs are fully automated.

3. Copy outputs to the run directory:
   ```bash
   cp -r $WORK_DIR/output $EVAL_DIR/runs/$RUN_ID/output
   cp -r $WORK_DIR/screenshots $EVAL_DIR/runs/$RUN_ID/screenshots
   ```

4. Save the exact prompt used:
   Write the creative brief + DESIGN.md + final prompt sent to /frontend-design
   to `$EVAL_DIR/runs/$RUN_ID/input-prompt.md`.

5. Save the design system used:
   Copy DESIGN.md to `$EVAL_DIR/runs/$RUN_ID/design-system.md`.

### Step 3: Score

Score each dimension 1-10 by analyzing the generated output.

**visual_quality (weight: 0.30)**
Read the desktop screenshot. Evaluate against professional marketing site
standards:
- Layout balance and visual hierarchy
- Typography quality (size contrast, line height, font pairing)
- Whitespace usage
- Overall polish and intentionality
Score 1-10. Write a one-sentence justification.

**brand_consistency (weight: 0.20)**
Read the generated HTML/CSS source and the brand guidelines from context.
Check mechanically:
- Font families match brand guidelines
- Color hex values match brand palette
- Overall tone matches brand voice guidelines
Count deviations. 0 deviations = 10, 1 = 9, 2 = 8, etc. Floor at 1.
Write which specific deviations were found.

**content_accuracy (weight: 0.25)**
Read the generated HTML text content and the product brief from context.
Extract key terms from the product brief (listed under "Key Terms" if
present, otherwise extract product name, feature names, value props).
Count how many appear in the generated output.
Score: (terms_found / total_terms) * 10, rounded.
Write which terms were found and which were missing.

**responsiveness (weight: 0.15)**
If multiple viewport screenshots exist (desktop, tablet, mobile), compare
them for layout breakage. If only desktop exists, check the HTML/CSS for
responsive patterns (media queries, flexible units, viewport meta tag).
Score 1-10 based on responsive design quality.

**code_quality (weight: 0.10)**
Read the generated HTML source. Check:
- Valid HTML structure (doctype, head, body)
- All images have alt text
- No broken resource references
- Viewport meta tag present
- Semantic HTML elements used (header, main, section, footer)
Count issues. 0 issues = 10, 1 = 9, 2 = 8, etc. Floor at 1.

**Composite score:**
```
overall = (visual * 0.30) + (brand * 0.20) + (content * 0.25) +
          (responsive * 0.15) + (code * 0.10)
```

### Step 4: Save Scores

Write `$EVAL_DIR/runs/$RUN_ID/scores.json`:

```json
{
  "run_id": "RUN_ID",
  "timestamp": "ISO_TIMESTAMP",
  "agent_version": "VERSION_FROM_PLUGIN_JSON",
  "dimensions": {
    "visual_quality": { "score": N, "notes": "..." },
    "brand_consistency": { "score": N, "notes": "..." },
    "content_accuracy": { "score": N, "notes": "...", "terms_found": N, "terms_total": N },
    "responsiveness": { "score": N, "notes": "..." },
    "code_quality": { "score": N, "notes": "...", "issues": N }
  },
  "overall": N.NN,
  "context_hash": "MD5_OF_CONTEXT_DIR",
  "vs_baseline": "+/-N.NN or null if no baseline"
}
```

### Step 5: Compare Against Baseline

Read `$EVAL_DIR/baseline.json`. If it has a non-null `run_id`:
- Calculate delta for each dimension and overall
- Report improvements and regressions

If no baseline set, note: "No baseline yet. Run with --update-baseline to set one."

### Step 6: Update History

Read `$EVAL_DIR/eval-history.json`. Append this run's scores to the `runs` array:

```json
{
  "run_id": "RUN_ID",
  "timestamp": "ISO_TIMESTAMP",
  "overall": N.NN,
  "visual_quality": N,
  "brand_consistency": N,
  "content_accuracy": N,
  "responsiveness": N,
  "code_quality": N
}
```

Write the updated file back.

### Step 7: Report

Print a formatted report:

```
╔══════════════════════════════════════════════════════════╗
║  EVAL: connect — Run 2026-03-25-v001                    ║
╠══════════════════════════════════════════════════════════╣
║  Dimension          Score    Baseline    Delta           ║
║  ─────────────────  ─────    ────────    ─────           ║
║  Visual Quality      7/10     —           —              ║
║  Brand Consistency   8/10     —           —              ║
║  Content Accuracy    9/10     —           —              ║
║  Responsiveness      6/10     —           —              ║
║  Code Quality        8/10     —           —              ║
║  ─────────────────  ─────    ────────    ─────           ║
║  OVERALL             7.55     —           —              ║
╠══════════════════════════════════════════════════════════╣
║  Run saved to: evals/connect/runs/2026-03-25-v001/      ║
║  Set as baseline: eval connect --update-baseline        ║
╚══════════════════════════════════════════════════════════╝
```

## --update-baseline

Read the most recent run from `$EVAL_DIR/runs/`. Copy its scores to
`$EVAL_DIR/baseline.json`. Confirm: "Baseline updated to run {RUN_ID}
(overall: {SCORE})."

## --history

Read `$EVAL_DIR/eval-history.json`. Print a table of all runs with scores.
If more than 5 runs exist, also print a trend summary:
"Trending UP/DOWN/FLAT over last N runs. Best: {run_id} ({score}).
Worst: {run_id} ({score})."

## --compare <run1> <run2>

Read scores.json from both runs. Print side-by-side comparison:
- Each dimension: run1 score vs run2 score, delta
- Overall: run1 vs run2
- If screenshots exist for both, note: "View screenshots at
  evals/{product}/runs/{run1}/screenshots/ and
  evals/{product}/runs/{run2}/screenshots/"
````

- [ ] **Step 2: Commit the skill**

```bash
git add plugins/canopy/skills/website-builder/
git commit -m "feat: add website-builder eval skill

Evaluation framework that scores generated websites on 5 dimensions
(visual quality, brand consistency, content accuracy, responsiveness,
code quality), tracks scores over time, and enables comparison between
runs.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Create the Command Wrapper

**Files:**
- Create: `plugins/canopy/commands/website-builder.md`

Follows the existing pattern — thin command wrapper that invokes the skill/agent.

- [ ] **Step 1: Write the command**

Create `plugins/canopy/commands/website-builder.md`:

```markdown
---
description: >
  Build marketing websites from product context, or run evaluation suites
  to measure and improve generation quality. Uses persistent memory for
  brand context. Use when asked to "build a website", "generate a page",
  "eval website", or "website-builder".
argument-hint: [generate|eval <product>|eval <product> --update-baseline|eval <product> --history|eval <product> --compare <run1> <run2>]
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion, Agent, Skill]
---

# Website Builder

Build marketing websites from product context or evaluate generation quality.

## Arguments

- `generate` (default) — Run the full generation pipeline from ./context/
- `eval <product>` — Run eval suite against fixed context in evals/<product>/
- `eval <product> --update-baseline` — Set most recent run as baseline
- `eval <product> --history` — Show score trends
- `eval <product> --compare <run1> <run2>` — Compare two runs
- No args: same as `generate`

## Process

For `generate`:
1. Check if this is being run as the `website-builder` agent (has memory).
   If yes, follow the agent's generate pipeline.
2. If running as a skill (no agent memory), read ./context/ directly and
   run the pipeline inline.

For `eval`:
1. Invoke the `website-builder` skill
2. Follow the eval workflow for the specified product
```

- [ ] **Step 2: Commit the command**

```bash
git add plugins/canopy/commands/website-builder.md
git commit -m "feat: add website-builder command wrapper

Thin command that routes to the agent (generate) or skill (eval).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Bump Plugin Version

**Files:**
- Modify: `plugins/canopy/.claude-plugin/plugin.json`
- Modify: `VERSION`

Per CLAUDE.md rules: always bump patch version, both files must match.

- [ ] **Step 1: Read current version**

```bash
cat plugins/canopy/.claude-plugin/plugin.json | grep version
cat VERSION
```

- [ ] **Step 2: Bump both files**

Current version is `0.2.10`. Bump to `0.2.11`.

Edit `plugins/canopy/.claude-plugin/plugin.json`: change `"version": "0.2.10"` to `"version": "0.2.11"`.

Edit `VERSION`: change `0.2.10` to `0.2.11`.

- [ ] **Step 3: Commit the version bump**

```bash
git add plugins/canopy/.claude-plugin/plugin.json VERSION
git commit -m "chore: bump version to 0.2.11 for website-builder agent

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Run First Eval (Smoke Test)

This task validates the entire pipeline works end-to-end.

- [ ] **Step 1: Set up a working directory for the eval**

```bash
mkdir -p /tmp/website-builder-test
cp -r evals/connect/context /tmp/website-builder-test/context
mkdir -p /tmp/website-builder-test/output
```

- [ ] **Step 2: Test context ingestion**

Read all files in `/tmp/website-builder-test/context/` and synthesize a
creative brief. Verify the brief contains:
- Product name: "CommCare Connect"
- At least 3 key terms from product-brief.md
- Tone profile from tone-reference.md
- Brand colors from brand-guidelines.md

- [ ] **Step 3: Test generation**

Invoke `/frontend-design` with the creative brief. Verify:
- Output files appear in `/tmp/website-builder-test/output/`
- At least one HTML file exists
- HTML contains product-specific content (not generic)

- [ ] **Step 4: Test QA**

Start local server, take screenshot, verify screenshot exists.

- [ ] **Step 5: Test scoring**

Score the generated output against the 5 dimensions. Write scores to
`evals/connect/runs/YYYY-MM-DD-v001/scores.json`. Verify all dimensions
have scores between 1 and 10.

- [ ] **Step 6: Commit the first eval run**

```bash
git add evals/connect/runs/
git commit -m "feat: first eval run for Connect website builder

First end-to-end evaluation run establishing initial scores.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 7: Set baseline**

Copy scores from the first run to `evals/connect/baseline.json`.
Update `evals/connect/eval-history.json` with the first entry.

```bash
git add evals/connect/baseline.json evals/connect/eval-history.json
git commit -m "feat: set initial Connect eval baseline

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```
