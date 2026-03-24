---
name: walkthrough
description: |
  Execute a demo walkthrough spec against a live app and generate a stakeholder-ready
  HTML slideshow with screenshots, AI quality scores, and run-to-run comparison.
  Use when asked to "run the walkthrough", "demo prep", or "walkthrough <name>".
version: 0.1.0
---

# /walkthrough: Demo-Driven Development

Execute a YAML demo spec against a live app using a headless browser. Generate a
stakeholder-ready HTML presentation with screenshots, narrative, and AI quality
evaluations. Iterate: run → review → fix → rerun until scores converge.

## Modes

- `/walkthrough <name>` — Execute `docs/walkthroughs/<name>.yaml`
- `/walkthrough generate` — Interactively create a new walkthrough spec
- `/walkthrough` (no args) — List available specs in `docs/walkthroughs/`

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

### 1. Find the browse binary

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

```bash
mkdir -p screenshots/walkthroughs
mkdir -p /tmp/walkthrough-screenshots
```

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

## Execution

For each scene in the spec:

### Scene Execution Pattern

1. **Announce the scene** to the user:
   "Scene {n}/{total}: {title} (as {persona_name})"

2. **Navigate and interact.** Read the `show` field and use your knowledge of the app
   and its URL structure to navigate to the right page. The `show` field is intentionally
   high-level — you figure out the clicks and navigation. Use the app's UI, links, and
   URL patterns to get where you need to be.

3. **Wait for content.** If the page has dynamic content (SSE, AJAX, animations):
   ```bash
   $B wait --networkidle
   ```

4. **Take screenshots.** First neutralize fixed/sticky elements so they don't
   overlap content in full-page captures:
   ```bash
   $B js "document.querySelectorAll('*').forEach(function(el){var s=getComputedStyle(el);if(s.position==='fixed'||s.position==='sticky')el.style.position='absolute'})"
   $B screenshot /tmp/walkthrough-screenshots/scene_{n}.png
   ```

5. **Show the screenshot to the user** using the Read tool on the PNG file.

6. **Evaluate AI quality** (if the scene has `ai_quality`):
   - Read the page text:
     ```bash
     $B text
     ```
   - Evaluate against the `ai_quality` rubric in the spec.
   - Score on **4 independent dimensions** (1-5 each). The overall scene score
     is the **lowest** of the four (weakest-link principle):

     **Content Quality** — Is the AI output actually good?
     - Quote the worst sentence you can find verbatim
     - Check for demo data artifacts (duplicate applicants, same person appearing twice, placeholder names)
     - Verify factual claims: do AI-cited numbers match what's on the page?
     - Stakeholder smell test: read it as the CEO — would anything embarrass you?
     - 5=specific and impressive, 3=correct but generic, 1=wrong or empty

     **Visual Presentation** — Does the AI output look polished?
     - Is markdown rendered (not raw `##` headers or `**bold**` showing)?
     - Does it have proper spacing, hierarchy, and styling?
     - Would it look professional in a stakeholder meeting?
     - 5=polished card/panel with styled content, 3=readable but plain, 1=raw text wall

     **Screenshot Quality** — Is the capture itself clean?
     - No overlapping fixed headers, no blank regions, no cut-off content
     - Full relevant content visible (not hidden below scroll)
     - No browser chrome, error modals, or dev tools visible
     - 5=perfect capture, 3=usable but has issues, 1=blank or broken

     **Demo Readiness** — Would you show this slide to a stakeholder?
     - Realistic data (real-looking org names, varied responses, proper amounts)
     - No "test-user", "Unknown Organization", "None None" visible
     - The narrative (impressive_because) actually matches what's shown
     - 5=stakeholder-ready, 3=needs polish, 1=not demoable

   - Write a 1-3 sentence commentary per dimension, plus the overall score.

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

10. **Screenshot troubleshooting.** If a screenshot comes back blank or shows the
    wrong content:
    - Pages with hidden sidebars or collapsed sections can inflate page height to
      millions of pixels, causing full-page screenshots to render blank
    - **Workaround:** Use JS to move the target element to the top of the page
      before capturing: `$B js "var el=document.querySelector('.target'); document.body.insertBefore(el, document.body.firstChild)"`
    - Alternatively, use viewport-only screenshots for problematic pages
    - If content is behind a scroll container, scroll it into view first

### Data Collection

As you execute scenes, build a JSON data structure. After all scenes complete,
write it to `/tmp/walkthrough-run-data.json`:

```json
{
  "name": "<from spec>",
  "narrative": "<from spec>",
  "generated_at": "<current ISO timestamp>",
  "duration_seconds": "<elapsed time>",
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
      "ai_evaluation": { "score": 4, "max_score": 5, "commentary": "..." }
    },
    {
      "type": "summary",
      "scenes_completed": "<count>",
      "scenes_total": "<total>",
      "ai_scores": [{ "feature": "<title>", "score": 4, "max_score": 5 }],
      "issues": [{ "scene": 1, "severity": "warning", "description": "..." }],
      "previous_run": "<previous sidecar JSON or null>"
    }
  ]
}
```

**Base64 encoding screenshots:**
```bash
base64 -i /tmp/walkthrough-screenshots/scene_{n}.png
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

Tell the user:
"Walkthrough complete! HTML deck saved to `screenshots/walkthroughs/<name>.html`.
Review it in your browser. Let me know if you want to fix anything and rerun."

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

## The Iteration Loop

The walkthrough is designed for iterative improvement:

1. **Run** — Execute the walkthrough, generate the deck
2. **Review** — User opens the HTML, spots issues (app bugs AND presentation problems)
3. **Fix** — Claude creates branches, implements fixes, creates PRs
4. **Rerun** — Verify improvements, compare scores against previous run via JSON sidecar

The summary slide automatically shows score progression when a previous run exists.
Each iteration should improve the average AI quality score. Target: 4.5+/5 before
declaring the demo stakeholder-ready.
