---
name: walkthrough
description: |
  Execute a demo walkthrough spec against a live app and generate a stakeholder-ready
  HTML slideshow with screenshots, AI quality scores, and run-to-run comparison.
  Core run procedure only — for improve/adversarial/eval modes, use the walkthrough agent.
  Use when asked to "run the walkthrough", "demo prep", or "walkthrough <name>".
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# /walkthrough: Demo-Driven Development

Execute a YAML demo spec against a live app using a headless browser. Generate a
stakeholder-ready HTML presentation with screenshots, narrative, and AI quality
evaluations.

## Modes

- `/walkthrough <name>` — Execute `docs/walkthroughs/<name>.yaml`
- `/walkthrough generate` — Interactively create a new walkthrough spec
- `/walkthrough` (no args) — List available specs in `docs/walkthroughs/`

For orchestrated improvement cycles, adversarial reviews, and eval tracking,
use the walkthrough **agent** (invoked via `/walkthrough improve`, `/walkthrough adversarial`,
or `/walkthrough eval`).

## YAML Spec Format

Walkthrough specs live in `docs/walkthroughs/<name>.yaml`:

```yaml
name: "Demo Name"
narrative: "One-line thesis for the demo"
base_url: "http://localhost:8000"

# Auth (optional — omit for public pages)
auth:
  type: url                    # "url" or "command"
  url: "/auth/login?token=dev" # for type: url — navigate here to authenticate

# For command-based auth:
# auth:
#   type: command
#   check: "python manage.py check_token"    # command to verify auth
#   login: "python manage.py get_token"      # interactive command (user runs with !)
#   inject_url: "/auth/set-token?token={token}"  # URL to inject the token

personas:
  alice:
    name: "Alice Smith"
    role: "Program Manager, Acme Corp"
    color: "#2563eb"
    intro: "Alice manages field programs and needs fast reporting."

scenes:
  - persona: alice
    title: "Dashboard overview"
    show: "Main dashboard with KPIs loaded"
    impressive_because: "Data loads in real-time, charts are interactive"
    ai_quality: "KPI descriptions should be specific to the program, not generic"  # optional
```

## Setup

### 1. Find the browse binary and set state file

```bash
_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
B=""
[ -n "$_ROOT" ] && [ -x "$_ROOT/.claude/skills/gstack/browse/dist/browse" ] && B="$_ROOT/.claude/skills/gstack/browse/dist/browse"
[ -z "$B" ] && B=~/.claude/skills/gstack/browse/dist/browse
if [ -x "$B" ]; then
  echo "READY: $B"
else
  echo "NEEDS_SETUP: run 'cd ~/.claude/skills/browse && ./setup'"
fi
```

**CRITICAL:** Set the browse state file to avoid lock conflicts and stale sessions.
Pick a fixed path for this walkthrough and use it for ALL browse commands in this run:
```bash
export BROWSE_STATE_FILE=/tmp/walkthrough-browse-<name>.json
```
Replace `<name>` with the walkthrough spec name (e.g., `baobab-demo`). Do NOT use `$$`
(shell PID) — it changes across Bash calls. Without this, the browse server will fail
with "Another instance is starting" if another session has used browse recently.

**After starting browse, verify it's pointing at the right app:**
```bash
$B goto <base_url>
$B text
```
If the page content is from a different app (e.g., you see "Fund Dashboard" when you
expected "Programs"), the browse session is stale. Kill it and restart with the state
file set.

### 2. Read the walkthrough spec

```bash
cat docs/walkthroughs/<name>.yaml
```

Parse the YAML to extract: `name`, `narrative`, `base_url`, `auth`, `personas`, `scenes`.

### 3. Check for previous run

```bash
SIDECAR="screenshots/walkthroughs/<name>.json"
[ -f "$SIDECAR" ] && cat "$SIDECAR" || echo "NO_PREVIOUS_RUN"
```

If a previous run exists, keep its data for the summary slide comparison.

### 4. Create output directories

**CRITICAL:** Use a per-walkthrough screenshot directory, not a shared global one.
Without this, screenshots from different projects or previous runs bleed through.

```bash
mkdir -p screenshots/walkthroughs
SHOT_DIR="/tmp/walkthrough-screenshots/<name>-$(date +%s)"
mkdir -p "$SHOT_DIR"
echo "Screenshots: $SHOT_DIR"
```

Use `$SHOT_DIR/scene_{n}.png` for all screenshots in this run. Never use a bare
`/tmp/walkthrough-screenshots/` — that's shared across all sessions and projects.

### 5. Authenticate

Handle auth based on the spec's `auth` block:

**If `auth.type` is `url`:**
```bash
$B goto <base_url><auth.url>
$B text
```
Verify the response indicates success (check for error messages).

**If `auth.type` is `command`:**
1. Run the check command to see if auth is already valid:
   ```bash
   <auth.check>
   ```
2. If expired or missing, tell the user to run the login command interactively:
   > "Your auth is expired. Please run this to re-authenticate:"
   > `! <auth.login>`
3. Wait for the user to confirm, then inject the token via `auth.inject_url`.

**If no `auth` block:** Skip authentication (public pages).

## Pre-flight Check

Before executing any scenes, verify the target app is healthy:

```bash
$B goto <base_url>
$B wait --networkidle
```

Check for:
- **CSS loading:** Does the page look styled? Check for 404s on CSS/JS bundles in
  console output. If assets are missing (common with worktree servers that haven't
  run a build step), STOP and tell the user: "The server at {base_url} is missing
  CSS assets — the app looks unstyled. Run the build step first."
- **Correct app:** Does the page content match what you expect? If you see content
  from a different app, the browse session is stale.
- **Server responding:** If the page is blank or shows a connection error, the server
  isn't running.

Do NOT proceed to scene capture if the pre-flight fails. Bad captures waste time
and the user will catch it before you do.

## Execution

For each scene in the spec:

### Scene Execution Pattern

1. **Announce the scene** to the user:
   "Scene {n}/{total}: {title} (as {persona_name})"

2. **Navigate and interact.** Read the `show` field and use your knowledge of the app
   and its URL structure to navigate to the right page. The `show` field is intentionally
   high-level — you figure out the clicks and navigation. Use the app's UI, links, and
   URL patterns to get where you need to be.

3. **Wait for the page to fully load.** Always wait for network idle before
   screenshotting — this catches SSE streaming, AJAX calls, lazy-loaded images,
   and chart rendering:
   ```bash
   $B wait --networkidle
   ```
   If the page still shows loading spinners or "loading..." text after networkidle,
   wait a few more seconds and check again with `$B text`.

4. **Take a full-page screenshot.**
   ```bash
   $B screenshot $SHOT_DIR/scene_{n}.png
   ```
   Always use full-page captures — the HTML deck makes slides scrollable, so tall
   pages are fine. Do NOT switch to `--viewport` screenshots.

   **If the screenshot is absurdly tall (10,000+ pixels):** This is a BUG in the app,
   not a screenshot problem. An infinitely growing element (e.g., Chart.js canvas with
   `maintainAspectRatio: false` in an unconstrained container) is making the page
   impossibly tall. Flag it as a **[CODE]** issue with Demo Readiness ≤ 2 and use the
   blocking rule — do NOT silently switch to viewport captures and score 4/5.

5. **Show the screenshot to the user** using the Read tool on the PNG file.

6. **Evaluate EVERY scene with the Tough Judge rubric.** You are the harshest reviewer
   this product will ever face. Your job is to find what's wrong, not to feel good about
   what's right. If you're scoring generously, you're scoring wrong.

   **Important prior:** if you built this product (or any part of this session was spent
   modifying it), your scores are inherently biased upward. Default to subtracting 1 from
   every dimension on reflection, and apply the cross-check below.

   Read the FULL page text carefully — every word, not just headings:

   ```bash
   $B text
   ```

   ### Phase 1: Adversarial listing (MANDATORY before any scoring)

   Before writing a single number, list:

   1. **Three most embarrassing things on this slide** if you had to pause and explain
      them to a skeptical CEO of a Fortune 500 company who is deciding whether to adopt
      your product. Be specific. Quote exact text, name exact UI elements.

      If you can't find three, you haven't looked hard enough. Common things to check:
      - Demo data artifacts ("Untitled", duplicate titles, "test-user", placeholder avatars)
      - Empty states dominating the frame (empty chat, "No data yet", blank charts)
      - Error or warning banners visible (even "by design" banners look bad in a demo)
      - Feature gaps the CEO would immediately ask about ("is that all Settings has?")
      - Visual issues (low contrast, cramped spacing, inconsistent icon sizes)
      - Claimed-but-not-shown behavior (narration says "streaming" but nothing streams)

   2. **Three ways a competitor does this better.** Name a real product in the same
      category (Linear, Notion, Slack, Vercel, Height, Superhuman, etc.) and describe
      concretely what they do that you don't. If you cannot name three, you are not
      thinking adversarially enough — look again.

   3. **The binary projector test.** Would you put this EXACT slide on a projector at
      an all-hands tomorrow morning, to an audience including your most demanding
      stakeholder, without ANY verbal caveats? Answer YES or NO. This answer is a hard
      gate on the Demo Readiness score below.

   Output these three lists as a block. Only then proceed to scoring.

   ### Phase 2: Score each dimension, starting from 3/5

   **EVERY dimension starts at 3/5.** A 3 is "functional but unremarkable — you can ship
   it, but nothing here makes a stakeholder lean forward." That is the DEFAULT. Every
   step up must be earned and justified with specific evidence. Every step down reflects
   a specific problem.

   - **5** — World-class. You genuinely cannot find anything to criticize after the
     adversarial pass above. This should be extraordinarily rare. If more than ~20% of
     scenes in a walkthrough land at 5, your bar is too low.
   - **4** — Strong, with one concrete thing a designer would polish if given another day.
     Name the one thing.
   - **3** — Functional. Ships. Nothing embarrassing, nothing delightful. **This is the
     default.**
   - **2** — Visible problem a careful viewer catches immediately. Demo data artifacts,
     loading states, empty content where there should be substance, misaligned claims.
   - **1** — Would actively damage credibility. Broken, wrong, or obviously unfinished.

   Apply this scale to all 5 dimensions below. The overall scene score is the LOWEST of
   all dimensions (weakest link). ALL scenes get scored, not just AI ones.

   **A. Content Quality** — the data/text/claims visible on this scene.

   For AI scenes: quote the worst sentence verbatim. Check for demo data artifacts
   (duplicate people/orgs, "Unknown Organization", identical responses) — any = max 2.
   Verify factual claims: numbers cited by AI must match the actual page data — wrong = max 3.

   For non-AI scenes: check DATA quality. "Untitled" entries = max 3. Empty charts
   where there should be data = max 3. Test/duplicate data visible = max 2. Real
   organization/user names instead of "alice@test.com" and friends.

   **B. App Page Quality** — how the actual product page looks (NOT the walkthrough slide).

   This evaluates the product being demoed. Does it look like shadcn/Linear/Superhuman,
   or does it look like a developer tool? Specifically check: visual hierarchy, spacing,
   type scale, icon consistency, button variant use, loading/empty state polish.

   Default 3. A 4 requires one specific "nice touch." A 5 requires "I would be proud to
   hire the designer who shipped this."

   **C. Screenshot Quality** — is the capture clean and complete?

   Default 3 if everything visible is on-topic. A 5 requires perfect framing with no
   wasted whitespace and no cutoff content. A 4 is slightly off (minor crop, slight
   scroll offset).

   **D. Walkthrough Slide Quality** — how THIS slide in the deck tells a story.

   Does the narration pay off in the screenshot? Does the slide highlight what's
   impressive, or is it just a raw dump? A 5 requires the reader to understand the
   product benefit without any verbal explanation. Default 3.

   **E. Demo Readiness** — the binary projector test, encoded.

   - **5** requires YES to the projector test AND the adversarial listing found nothing
     substantive to fix.
   - **4** requires YES to the projector test with ONE named caveat.
   - **3** — "only if I skip this slide or narrate around the rough spots."
   - **2** — "I'd preface it with 'still a prototype' or have a backup slide ready."
   - **1** — "I wouldn't show this at all."

   ### Phase 3: Cross-check (sanity floor)

   After scoring, check these sanity rules:

   - **If ANY of your top-3 embarrassing things is unfixed in the screenshot, Demo
     Readiness cannot exceed 3.** No exceptions.
   - **If the projector test answer is NO, Demo Readiness cannot exceed 3.**
   - **If a competitor does it obviously better in all 3 named ways, App Page cannot
     exceed 3.**
   - **If average of all scenes in the walkthrough is above 4.0, you are almost
     certainly scoring too generously.** Re-read each scene's adversarial pass and
     revise downward.
   - **If you are the author of the code shown**, subtract 1 from every dimension
     unless you can justify in writing why your self-scoring is calibrated.

   ### Phase 4: Required output format

   Output this exact format for every scene. Do not skip sections. Do not fabricate
   scores. You MUST have run `$B text` and looked at the screenshot before scoring.

   ```
   ### Scene {n}: {title}

   **Top-3 embarrassing things (adversarial):**
   1. "{verbatim quote or specific UI description}"
   2. "{verbatim quote or specific UI description}"
   3. "{verbatim quote or specific UI description}"

   **Three ways a competitor does this better:**
   1. {Product} — {specific thing they do that we don't}
   2. {Product} — {specific thing they do that we don't}
   3. {Product} — {specific thing they do that we don't}

   **Projector test:** YES / NO — {one-sentence reasoning}

   A. Content:      {1-5}/5 — {one sentence justifying any deviation from 3}
   B. App Page:     {1-5}/5 — {one sentence}
   C. Screenshot:   {1-5}/5 — {one sentence}
   D. Slide:        {1-5}/5 — {one sentence}
   E. Demo Ready:   {1-5}/5 — {must be consistent with projector test}

   Overall: {lowest}/5 (weakest: {dimension name})
   Author-of-code penalty applied: YES / NO
   Fix: [{CODE|SPEC|DATA|INFRA}] {concrete fix description}
   ```

   If any of the 5 sections above is missing, the scoring is invalid and you must redo
   it. Do not shortcut this format even under time pressure — shortcutting is how
   inflated scores happen.

   **BLOCKING RULE:** If ANY scene scores 2 or below on Demo Readiness, STOP the
   walkthrough IMMEDIATELY and tell the user:

   > "Scene {n} scored {score}/5 on Demo Readiness — this would hurt the demo.
   > Page: {full URL that was loaded for this scene}
   > The issue is: {quote the problem}. Recommended fix: {fix}.
   > Should I fix this now before continuing, or skip this scene?"

   Always include the **full URL** so the user can open the page directly and
   confirm the issue before deciding how to proceed.

   Do NOT silently log a 2/5 and keep going. A 2/5 means the slide would embarrass
   you in a meeting — that's a blocker, not a warning. Either fix it or drop it.

   **NEVER fabricate scores.** If you did not run `$B text` and read the page content
   for a scene, you cannot score it. If you are building a JSON data file and writing
   scores inline, you are doing it wrong — score each scene interactively after
   viewing the screenshot and reading the page text.

### Fixing Data Issues

When a scene fails due to bad demo data (`[DATA]` issues — duplicates, placeholder names,
missing records, wrong values), **do not try to fix data through the browser**. The browser
is for observing and verifying, not for clicking edit/delete links or submitting forms.

Instead, step into the codebase:

1. **Understand the data layer.** Read the app's models, views, and API endpoints to
   understand how the data is structured and how it's created/updated/deleted. Use Grep
   and Read — not the browser — to find the relevant code.

2. **Check for existing tools.** Look for:
   - Management commands (e.g., `python manage.py seed_data`, `create_demo_data`)
   - Fixture files or seed scripts
   - REST/GraphQL API endpoints for CRUD operations
   - Available MCP tools that interact with the app's data layer

3. **Fix through the proper interface.** Use the app's own APIs, management commands,
   or ORM-level scripts to create, update, or delete data. This is faster, more reliable,
   and less error-prone than navigating forms in a headless browser.

4. **Verify through the browser.** After making the data fix, re-navigate to the scene's
   page in browse and confirm the issue is resolved before re-scoring.

The system IS allowed to mutate data — on localhost or production — but it should do so
by understanding the codebase's data APIs, not by fumbling through UI forms.

7. **Record issues.** If anything goes wrong (element not found, page error, slow load,
   empty state), note it as an issue with severity (error/warning) and description.

8. **Handle failures gracefully.** If a scene can't complete:
   - Screenshot the error state
   - Log the issue
   - Skip to the next scene
   - Partial decks are better than no deck

9. **Flag test data problems.** Before taking a screenshot, check for signs that
   test/sample data doesn't look realistic:
   - Organization names like "Unknown Organization" or "None None"
   - Placeholder usernames like "test-user" or blank names
   - Empty states that should have data (charts with "no data", maps with no markers)
   - Duplicate entries (same person/org appearing multiple times with identical content)
   - IDs or slugs showing instead of human-readable names
   If found, note it as an issue so the user knows the demo won't look right
   with this data.

### Data Collection

As you execute scenes, build a JSON data structure. After all scenes complete,
write it to `/tmp/walkthrough-run-data.json`:

```json
{
  "name": "<from spec>",
  "narrative": "<from spec>",
  "generated_at": "<current ISO timestamp>",
  "duration_seconds": 180,
  "personas": "<from spec — the full personas dict>",
  "slides": [
    { "type": "title" },
    { "type": "persona_intro", "persona_key": "<first persona>" },
    {
      "type": "scene",
      "scene_index": 1,
      "scene_total": "<total scenes>",
      "persona_key": "<persona>",
      "title": "<scene title>",
      "narration": "<impressive_because from spec>",
      "screenshot_b64": "<base64 encoded PNG>",
      "ai_evaluation": {
        "score": 3,
        "max_score": 5,
        "commentary": "Overall: 3/5 (weakest: Content). A: Content 3/5 — generic. B: App Page 4/5 — clean. C: Screenshot 4/5 — good. D: Slide 4/5 — clear. E: Demo Ready 3/5 — needs polish."
      }
    },
    {
      "type": "summary",
      "scenes_completed": "<count>",
      "scenes_total": "<total>",
      "ai_scores": [{ "feature": "<title>", "score": 3, "max_score": 5 }],
      "issues": [{ "scene": 1, "severity": "warning", "description": "..." }],
      "previous_run": "<previous sidecar JSON or null>"
    }
  ]
}
```

**IMPORTANT:** `duration_seconds` MUST be an integer, not a string. `ai_evaluation.score`
must be the LOWEST of the 5 dimension scores (weakest-link). The commentary must include
all 5 dimension scores in the format shown above.

**Base64 encoding screenshots:**
```bash
base64 -i $SHOT_DIR/scene_{n}.png
```

**Persona intro slides:** Insert a `persona_intro` slide before the first scene
of each new persona.

## Generate Presentation

After collecting all data, find the generator script:

```bash
# Check canopy repo locations
GEN=""
for P in \
  ~/emdash-projects/canopy/scripts/walkthrough/generate_presentation.py; do
  [ -f "$P" ] && GEN="$P" && break
done
# Fallback: check if project has a local copy
[ -z "$GEN" ] && [ -f "tools/walkthrough/generate_presentation.py" ] && GEN="tools/walkthrough/generate_presentation.py"
echo "${GEN:-NOT_FOUND}"
```

Run it:
```bash
python3 "$GEN" --input /tmp/walkthrough-run-data.json --output screenshots/walkthroughs/<name>.html
```

Then open the result:
```bash
open screenshots/walkthroughs/<name>.html
```

## Verify Deck (MANDATORY — do not skip)

After generating the HTML deck, you MUST verify your own output before presenting
it to the user. The deck may contain problems invisible during live browsing:

1. **Open the deck in browse:**
   ```bash
   $B goto file://$PWD/screenshots/walkthroughs/<name>.html
   ```

2. **Navigate to each scene slide** and take a viewport screenshot. For each slide:
   - Read the screenshot with the Read tool
   - Does the embedded screenshot show the right page? (not a different app, not a stale capture)
   - Is the content styled? (not raw unstyled HTML from a server missing CSS)
   - Are there loading spinners, black screens, or blank areas?
   - Does the score shown match what the screenshot actually looks like?

3. **Flag mismatches.** If any slide's screenshot doesn't match the score you gave it
   during live browsing, update the score and note the discrepancy. Common problems:
   - Screenshot captured from wrong server (worktree without built CSS)
   - Screenshot captured before page finished loading (spinners visible)
   - Screenshot shows a different page than expected (stale browse session)
   - Screenshot is absurdly tall or blank

4. **Report to the user** with confidence level:
   - "Deck verified — all slides match their scores" (if everything checks out)
   - "Deck has issues — slides {n, m} need retaking: {reasons}" (if problems found)

**Do NOT tell the user the deck is ready without verifying it yourself.**
The user should never be the first person to catch a bad screenshot.

## Generate Mode

When invoked as `/walkthrough generate`:

1. Ask the user what feature or demo they want to walk through.
2. Check for existing design docs:
   ```bash
   grep -rl "Demo Narrative\|walkthrough\|demo" docs/plans/ docs/designs/ 2>/dev/null
   ```
3. If found, use it as the starting point. If not, ask the user to describe the scenes.
4. For each scene, ask: What persona? What should be shown? What makes it impressive?
   Does it have AI output to evaluate?
5. Write the YAML to `docs/walkthroughs/<name>.yaml`.
6. Offer to execute it immediately.

## Efficient Reruns

When rerunning after fixes, don't re-run all scenes:

- **Selective retake:** If 2 of 8 scenes need fixing after code changes, retake only
  those screenshots. Keep the good captures from the previous run.
- **Screenshot reuse:** If the underlying data hasn't changed for a scene, reuse the
  previous run's screenshot rather than recapturing (avoids fighting capture issues).
- **Incremental fixes:** Fix the lowest-scoring scenes first. Each fix-and-retake cycle
  should target the biggest Demo Readiness blockers.
