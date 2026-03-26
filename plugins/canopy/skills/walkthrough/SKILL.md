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
[ -n "$_CANOPY_UPD" ] && echo "$_CANOPY_UPD"
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

6. **Evaluate EVERY scene.** Be an extremely tough judge. You are evaluating whether
   this is ready to project in front of a stakeholder deciding whether to use this product.

   Read the FULL page text carefully — every word, not just headings:

   ```bash
   $B text
   ```

   Score on **5 dimensions**. The overall scene score is the **LOWEST** of all applicable
   dimensions (weakest link). ALL scenes get scored, not just AI ones.

   **A. Content Quality** (EVERY scene, not just AI):

   For AI scenes (`ai_quality` in spec): You MUST read the AI output word by word. Do not skim.

   - **Quote the worst sentence** verbatim. If you can't find anything bad, score may be high.
   - **Check for demo data artifacts:** same person/org appearing multiple times as different
     applicants, "Unknown Organization", "None None", identical responses. Any = max 2.
   - **Verify factual claims:** numbers cited by AI must match the actual page data. Wrong = max 3.
   - **Stakeholder smell test:** read as the CEO of the company being demoed to. What makes you raise an eyebrow?

   For non-AI scenes: Check the DATA on the page.

   - Are KPIs populated or showing "loading..."/"—"?
   - Do organization/user names look real or like test data?
   - Are charts populated with meaningful data or empty?
   - Do numbers make sense (e.g., $0 distributed, 0 users)?
   - Is there anything embarrassing a stakeholder would notice?

   Scoring:

   - **5** — All data/content accurate, specific, and impressive. Nothing embarrassing.
   - **4** — Mostly good but one item is slightly off or one field shows placeholder data
   - **3** — Noticeable issues a careful reader would catch (loading states, generic content)
   - **2** — Demo data artifacts, wrong facts, or embarrassing content
   - **1** — Would actively damage credibility

   **B. App Page Quality** — How does the actual product page look? (NOT the walkthrough slide)
   This evaluates the actual product being demoed, not the walkthrough HTML.

   - **5** — Professional, polished UI a designer would approve. Clear hierarchy, good spacing.
   - **4** — Good layout but one area feels cramped or unpolished
   - **3** — Functional but looks like a developer tool — dense text, no visual hierarchy
   - **2** — Messy layout, overlapping elements, broken styling
   - **1** — Broken or unusable

   **C. Screenshot Quality** — Is the capture clean and complete?

   - **5** — Clean, properly framed, content starts at top, nothing cut off
   - **4** — Good but slightly cropped or minor framing issue
   - **3** — Content visible but awkwardly framed — header overlap, too much whitespace
   - **2** — Important content missing or wrong scroll position
   - **1** — Wrong page, blank, or mostly empty

   **D. Walkthrough Slide Quality** — How does THIS SLIDE in the deck look?
   This evaluates the walkthrough presentation, not the app.

   - **5** — Screenshot is readable, narration tells the story, persona badge is clear
   - **4** — Good but narration could be more specific or screenshot needs scroll to see key part
   - **3** — Slide works but doesn't highlight the impressive thing about this scene
   - **2** — Screenshot dominates with no clear story, or narration is generic
   - **1** — Slide adds no value — just a raw screenshot dump

   **E. Demo Readiness** — Would you show this to the stakeholder without apologizing?

   - **5** — Yes, confidently. Clear story, polished look, accurate content.
   - **4** — Yes, with one minor caveat
   - **3** — Maybe, but you'd talk over the rough spots
   - **2** — You'd skip this slide or preface with "still a prototype"
   - **1** — Would hurt credibility

   **MANDATORY: Output this exact format for every scene.** Do not skip dimensions.
   Do not fabricate scores without reading the page. You MUST run `$B text` and read
   the output before scoring.

   ```
   ### Scene {n}: {title}
   Worst thing found: "{verbatim quote from page content}"

   A. Content:      {1-5}/5 — {one sentence}
   B. App Page:     {1-5}/5 — {one sentence}
   C. Screenshot:   {1-5}/5 — {one sentence}
   D. Slide:        {1-5}/5 — {one sentence}
   E. Demo Ready:   {1-5}/5 — {one sentence}

   Overall: {lowest}/5 (weakest: {dimension name})
   Fix: [{CODE|SPEC|DATA|INFRA}] {concrete fix description}
   ```

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
  ~/emdash-projects/canopy-orchestrator/scripts/walkthrough/generate_presentation.py \
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
