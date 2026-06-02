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

All run modes accept `--scene <selector>` to render only a subset of
scenes. See **Scene filter** below.

For orchestrated improvement cycles, adversarial reviews, and eval tracking,
use the walkthrough **agent** (invoked via `/walkthrough improve`, `/walkthrough adversarial`,
or `/walkthrough eval`).

## Scene filter (`--scene`)

Use this when you've just shipped a change that affects one scene and want
to re-grade THAT scene under the canonical 5-dimension rubric, instead of
re-running the whole spec.

**Why it exists:** without it, single-scene iteration drifts off the DDD
path — people screenshot and "verify" manually, skipping the rubric. The
filter lets the canonical pipeline run end-to-end on a subset, so the
judge, the deck, and the eval history stay consistent.

### Selector syntax

| Form | Meaning |
|------|---------|
| `--scene 2` | Just scene 2 (1-based index) |
| `--scene 2,4,5` | Scenes 2, 4, and 5 |
| `--scene 2-4` | Inclusive range — scenes 2, 3, 4 |
| `--scene name-match` | Case-insensitive substring match against scene `title` or `spine_id` |

If the selector matches **zero** scenes, STOP and tell the user:

> "Selector `<sel>` matched no scenes in <spec>. Spec has scenes: 1=<t1>,
> 2=<t2>, ... Pick a different selector or omit `--scene` to run all."

If the selector matches **all** scenes, treat it the same as no filter and
say so once: "selector matched all N scenes — equivalent to a full run."

### Behavior contract

1. **Preserve original scene indices.** A single-scene run for spec scene
   2 still labels the output "Scene 2 of N" in narration and the deck —
   NOT "Scene 1 of 1". This keeps comparison against full-spec runs
   honest (a scene-2 score from a partial run is directly comparable to
   a scene-2 score from a full run).

2. **Tag the sidecar.** Add two fields to `/tmp/walkthrough-run-data.json`:
   - `scenes_run: [2]` — the list of scene_index values actually rendered
   - `scene_filter: "2"` — the raw selector string from `--scene`

   Downstream tooling (deck generator, video recorder, eval history,
   `ddd-run` convergence reporter) reads these to distinguish partial
   runs from full runs.

3. **Run the full rubric.** The 5-dimension rubric still applies per
   scene. `--scene` only changes WHICH scenes get rendered, not how
   they're judged. Do not skip the blocking rule, do not weaken
   `canopy:visual-judge`, do not skip the cross-walkthrough sanity floor
   (it just operates on the filtered set).

4. **Single-scene caveats.** With one scene rendered, the "cross-scene
   sanity floor" loses some statistical power — log "scene-filter mode:
   sanity floor weak (n=1)" in the summary but still apply it.

5. **Improve mode.** `/walkthrough improve <name> --scene 2` iterates
   until scene 2 passes 4+ on all dimensions, then stops. The composite
   in the final report should say "(scene 2 graded; scenes 1,3,4,5 not
   re-run this iteration)".

6. **Eval mode.** `/walkthrough eval <name> --scene 2` writes to
   `screenshots/walkthroughs/<name>/runs/YYYY-MM-DD-vNNN-scene2/` (note
   the `-scene<sel>` suffix on the run dir). Does NOT overwrite the
   full-spec baseline. `--update-baseline` with `--scene` is rejected —
   baselines must be full-spec runs, not partials.

### Parsing the selector

Use this Python snippet (or equivalent) once at the start of the run:

```python
def select_scenes(spec_scenes, selector):
    """Return list of (orig_index, scene_dict) tuples to actually run.
    orig_index is 1-based and preserved through the rest of the pipeline.
    """
    indexed = list(enumerate(spec_scenes, start=1))
    if not selector:
        return indexed
    sel = selector.strip()
    # 2-4 (range)
    if "-" in sel and all(p.strip().isdigit() for p in sel.split("-", 1)):
        a, b = (int(p) for p in sel.split("-", 1))
        return [(i, s) for i, s in indexed if a <= i <= b]
    # 2,4,5 (list)
    if "," in sel and all(p.strip().isdigit() for p in sel.split(",")):
        wanted = {int(p) for p in sel.split(",")}
        return [(i, s) for i, s in indexed if i in wanted]
    # single index
    if sel.isdigit():
        n = int(sel)
        return [(i, s) for i, s in indexed if i == n]
    # title / spine_id substring (case-insensitive)
    needle = sel.lower()
    return [
        (i, s) for i, s in indexed
        if needle in (s.get("title", "") or "").lower()
        or needle in (s.get("spine_id", "") or "").lower()
    ]
```

The rest of the procedure (auth, pre-flight, scene execution, judging,
deck generation, video recording) is identical — it just iterates over
the filtered subset instead of `spec.scenes` directly.

## YAML Spec Format

Walkthrough specs live in `docs/walkthroughs/<name>.yaml`:

```yaml
name: "Demo Name"
narrative: "One-line thesis for the demo"
base_url: "http://localhost:8000"

# Silent video recording (optional — see "Record Video" section)
record_video: true              # default: false
video_pace: fast                # fast | medium | slow (default: fast)
video_viewport_width: 1280      # default: 1280
video_viewport_height: 720      # default: 720

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
    video_hold_seconds: 8         # optional — dwell this long instead of scroll-paced timing
    viewport: { width: 1440, height: 900 }  # optional — per-scene viewport override
                                            # (this scene only; other scenes stay at the
                                            # spec-level video_viewport_width/height)
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

### Target identity: announce and don't substitute

Every spec has an implicit or explicit **target** — the specific slug, id, entity,
or URL path its scenes are written against (e.g., a named opportunity, a project
id, a user account). Before Scene 1:

1. **State the target in one line.** Name the identifier and what's visible about
   its state right now:
   > "Target: `<identifier>`, <N>/<M> preconditions met (e.g. 1/19 skills complete).
   > Spec asserts: `<key ai_quality or show claim>`."
2. **If the visible state falsifies the spec's premise, STOP.** Don't guess, don't
   improvise a save, don't pivot. Ask the user:
   > "Spec targets `<X>` and asserts `<Y>`, but the live state shows `<Z>`. Options:
   > (1) fix the data, (2) switch target (requires spec edit), (3) truncate to the
   > scenes that do work, (4) abort. Which?"

**You may NOT silently substitute a different target.** If scenes 2–5 can't run
against `<X>` and you find `<X2>` looks more populated, that is not authorization
to switch — it's a signal to ask. Silent substitution breaks the narrative premise
and the user will catch it.

## Execution

For each `(orig_index, scene)` in the filtered scene list (see **Scene
filter** for the selector logic — when `--scene` is omitted, the filtered
list IS the full `spec.scenes`):

### Scene Execution Pattern

1. **Announce the scene** to the user using the **original spec index**:
   "Scene {orig_index}/{spec_total}: {title} (as {persona_name})"

   With a scene filter, mention it once at the top:
   > "Scene filter active: `--scene <sel>` → running {len(filtered)} of {spec_total} scenes (indices: {orig_indices})."

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

6. **Evaluate the scene via `canopy:visual-judge`.**

   Capture the page text first (anchor for verbatim-quote scoring):

   ```bash
   PAGE_TEXT=$($B text)
   ```

   Dispatch the visual judge with walkthrough's rubric and the
   scene's narrative anchors:

   ```
   Skill('canopy:visual-judge', args={
     screenshot_path: "$SHOT_DIR/scene_{n}.png",
     page_text:       <PAGE_TEXT>,
     rubric:          <load skills/walkthrough/rubric.yaml verbatim>,
     context: {
       audience: { name: "skeptical CEO of a Fortune 500", decision: "deciding whether to adopt your product" },
       competitors: ["Linear", "Notion", "Slack", "Vercel", "Height", "Superhuman"],
       projector_test_phrasing: "Would you put this EXACT slide on a projector at an all-hands tomorrow morning, to an audience including your most demanding stakeholder, without ANY verbal caveats?",
       narrative_anchors: [<scene.impressive_because>, <scene.ai_quality>],
       blocking_rules: ["demo_readiness_low", "narrative_falsified"],
     },
   })
   ```

   The judge runs the Tough Judge methodology
   (adversarial listing → score-from-3 default → projector test → cross-check)
   and returns a verdict object with per-dimension scores + adversarial
   listing + projector test result + fix recommendation. Walkthrough's
   5 dimensions live in `rubric.yaml` (Content / App Page / Screenshot
   / Slide / Demo Readiness). The methodology was extracted from this
   skill into `canopy:visual-judge` in v0.2.79; per-rubric scoring
   conventions (start-from-3, weakest-link overall, projector-gate)
   are preserved verbatim.

   **Blocking-rule handling.** If the verdict comes back with
   `verdict: "blocked"` (either Demo Readiness ≤ 2, or scene-1/2
   narrative falsified), STOP the walkthrough IMMEDIATELY and tell
   the user:

   > "Scene {n} scored {dim.score}/5 on {dim.label} — this would
   > hurt the demo.
   > Page: {full URL that was loaded for this scene}
   > The issue is: {verdict.fix_recommendation}.
   > Should I fix this now before continuing, or skip this scene?"

   Always include the full URL so the user can open the page directly
   before deciding. Do NOT silently log a 2/5 and keep going.

   **Cross-walkthrough sanity floor.** After all scenes complete (or
   the loop blocks): if the average overall_score across scenes is
   > 4.0, you are almost certainly scoring too generously. Re-run
   any scene whose adversarial listing was thin and revise downward.
   This sanity rule applies at the WALKTHROUGH level (across scenes)
   and is enforced HERE, not in canopy:visual-judge (which is per-
   screenshot).

   **NEVER fabricate scores.** Don't construct a verdict by hand —
   always invoke `canopy:visual-judge` so the methodology stays
   consistent across rubrics + future evals that consume the same
   judge.

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
  "scenes_run": [2],
  "scene_filter": "2",
  "slides": [
    { "type": "title" },
    { "type": "persona_intro", "persona_key": "<first persona>" },
    {
      "type": "scene",
      "scene_index": 2,
      "scene_total": "<total scenes IN THE SPEC, not the filtered count>",
      "persona_key": "<persona>",
      "title": "<scene title>",
      "narration": "<impressive_because from spec>",
      "url": "<full URL that was screenshotted, including query string>",
      "logged_in_as": "<auth profile / username active when captured, e.g. 'ace' or 'ace@dimagi-ai.com'>",
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

**Scene-filter fields.** `scenes_run` is a JSON array of the original 1-based
spec indices that were actually rendered (e.g. `[2]` for a single-scene
run; `[1, 2, 3, 4, 5]` for a full run). `scene_filter` is the raw selector
string from `--scene`, or `null` for a full run. Both fields MUST be
present even on full runs (use `scenes_run: [1, 2, ..., N]` and
`scene_filter: null`) so consumers can always check shape unconditionally.

**Capture `url` and `logged_in_as` for every scene.** These render as a context row under
the slide title so a viewer can tell at a glance where the screenshot came from and under
which account. Use `$B url` right before the screenshot to grab the full current URL
(including query string), and use the auth profile name from the spec's `auth` block
(`--profile <name>` or `profile=<name>` in `inject_url`). Without these fields, the
context row is hidden — decks still render, but viewers lose that grounding.

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

## Record Video (optional)

If the spec sets `record_video: true`, produce a silent mp4 walkthrough
alongside the HTML deck. The recorder runs AFTER scoring and deck
generation — it replays each scene's captured URL through a fresh
Playwright Chromium context with `record_video` enabled, then converts
the resulting webm to mp4 via ffmpeg. Screenshots, scores, and the deck
are untouched.

**Skip this section entirely if `record_video` is not set or is false.**

### Interactive recording — scene `actions` (cursor + clicks)

The recorder injects a **synthetic cursor** (`_lib/cursor_overlay.js`) on every
context, so the mouse is visible and clicks draw a ripple. A scene with no
`actions` falls back to a scroll-pan (a static page tour). A scene that declares
`actions` is **driven** — the recorder glides the cursor and performs each step,
so the video shows the feature being *used*, not just displayed. This is what
lifts the `feature_use` score off the floor — a demo where nothing is clicked
reads as a slideshow.

Declare `actions` per scene in the spec (see `ddd-spec` for authoring + the
`Action` schema in `scripts/ddd/schemas/models.py`). Verbs: `goto`, `click`,
`click_menu`, `fill`, `select`, `type`, `press`, `hover`, `scroll_to`,
`scroll`, `wait_for`, `hold`. Each action is
`{kind, target?, value?, seconds?, note?}`; `target` is visible text OR a CSS
selector. For `kind: select` (native `<select>` controls — which `click`
can't reliably open across platforms), `value` is the option's `value`
attribute / a digit-only string as the 0-based index / the visible label —
recorder tries each in order. Example:

```yaml
scenes:
  - persona: maya
    title: "Maya tunes the plan"
    url: "/microplans/program/133/setup/"
    show: "exclude an invalid work area and watch the metrics update"
    actions:
      - { kind: wait_for, target: "PLAN METRICS" }
      - { kind: scroll_to, target: "Exclude" }
      - { kind: click, target: "Exclude", note: "drop an invalid area" }
      - { kind: wait_for, target: "Excluded 1" }
      - { kind: hold, seconds: 1.5 }
```

A bad/missing action target is logged and skipped — never fatal. The primitives
live in `scripts/walkthrough/_lib/recorder.py` (`execute_action` dispatcher).

**Anti-pattern — don't write both `url:` AND a leading `goto target: <same-url>`.**
The recorder navigates from `scene.url` automatically at the top of every scene. A
duplicate leading `goto` to the same path causes a visible page reload ~1-2s into
every scene (the page already loaded once, and now it loads again). Pick one:
`url:` is the declarative entry point — a `goto` action is only for navigating
**mid-scene** to a DIFFERENT page. The recorder strips redundant leading gotos as a
safety net (canopy 0.2.151+) but the spec should still read as authored — don't
lean on the strip.

**Open with `wait_for`, not a `hold`.** When the scene starts on a page that takes
a moment to render, the first action should be `{kind: wait_for, target: <text or
selector>}`. `wait_for` exits the instant the page is ready; `hold` always burns
its full duration. As a bonus, a leading `wait_for` tells the recorder to skip its
default `initial_hold_ms` + `goto_settle_ms` blind pauses (canopy 0.2.151+) — the
wait_for IS the settle, so the holds are pure dead air on top.

**Long waits use `wait_for seconds:`, not `hold seconds:`.** For waits that can
exceed the default 12s (a 30-90s bulk import, a slow background job), use the
`seconds:` override on `wait_for`:
```yaml
- { kind: wait_for, target: "Created 10 of 10 plans", seconds: 120 }
```
NOT `{kind: hold, seconds: 90}` — `wait_for` exits the instant the success text
appears; `hold` always burns the full 90s even if the job finished in 15.

**Don't `wait_for` on a transient intermediate state.** When a button's label
flickers through `"Creating N plans…"` → `"Created N of N plans"` faster than
the resolver can poll, a `wait_for` on the intermediate text races (~50% miss
rate) and the run report's "failed" column fills with false positives. Worse,
the spec author can't tell whether the failure means "something broke" or
"this transient text was too fast."

Pattern: wait only on TERMINAL states — the success card that doesn't replace
itself, the toast that stays for 5 seconds, the page heading that sticks. Use
`seconds:` to extend the timeout for long-running terminal waits.

```yaml
# ✗ Anti-pattern — races on the intermediate flicker
- { kind: click, target: "Create 10 plans" }
- { kind: wait_for, target: "Creating 10 plan" }   # ← races, often "fails"
- { kind: wait_for, target: "Created 10 of 10 plans" }

# ✓ Pattern — wait only on the terminal success state
- { kind: click, target: "Create 10 plans" }
- { kind: wait_for, target: "Created 10 of 10 plans", seconds: 120 }
```

**Target resolution syntax — prefer prefixes over bare CSS.** Every action's
`target` field can use a prefix to control how the recorder resolves it. Bare
strings use a heuristic (CSS-shaped → selector engine; English → visible-text
ranking via Playwright `get_by_role` / `get_by_text`), which is fine for most
cases. When the heuristic gets it wrong, or you want to be explicit, use a
prefix:

| Prefix | Routes to | When to use |
| --- | --- | --- |
| `css:#cfg-strategy` | `page.locator(...)` | Explicit CSS selector. Use when bare target gets mis-heuristic'd. |
| `testid:plan-picker` | `page.get_by_test_id(...)` | When the page exposes `data-testid` — the most refactor-resistant target type. |
| `aria:Resolved wards` | `page.get_by_label(...)` (accessible-name semantics, NOT raw `aria-label`) | Picks up `aria-label`, `aria-labelledby`, `<label for>`, `<label>` wrapping. |
| `role:button` or `role:button:Sign in` | `page.get_by_role(...)` (optional `name=...`, `exact=True`) | Playwright's recommended PRIMARY selector. |
| `text:Resolved wards` | `page.get_by_text(...)` | Forces visible-text path. Use when the text starts with `#` / `.` etc. and would otherwise be heuristic-routed as a selector. |

```yaml
actions:
  - { kind: click, target: "testid:bulk-paste-cta" }
  - { kind: click, target: "role:button:Sign in" }
  - { kind: wait_for, target: "Resolved wards" }   # bare text — heuristic routes correctly
```

Anti-pattern: don't write a fragile `:nth-of-type` CSS path when a `testid:`
would survive a sidebar refactor. Same for `nth-child` chains pointing at
unstable structural positions — those targets silently break the day someone
reorders a list, and the failure mode is "this action was skipped" buried in
the run report, not a loud failure.

**`must_succeed: true` for critical actions.** Default behavior: a failed
action prints a warning and the recording continues — one bad step never
aborts the render. This is right for the common case, but it hides cascade
failures: if scene 2's "Create" button click silently misses, every later
scene records against the wrong page state and the report says "60/61 actions
ok" while the whole demo is wrong.

Opt in with `must_succeed: true` on actions whose failure makes the rest of
the scene gibberish. Common candidates: the form-submit click that creates
the entity later scenes operate on; the navigation that lands on the page
later scenes screenshot.

The recorder raises `ActionAssertError` instead of swallowing — the scene
aborts loudly and the report flags it.

```yaml
actions:
  - { kind: fill, target: "#ward-list", value: "Galinja\nMadobi" }
  - { kind: click, target: "Create 10 plans", must_succeed: true }
  - { kind: wait_for, target: "Created 10 of 10 plans", seconds: 120, must_succeed: true }
```

When NOT to use it: `scroll_to`, `hold`, `hover` — these are pacing/framing
actions whose failure doesn't change product state. A skipped `scroll_to`
costs a smoother camera pan, not a wrong demo.

**Per-scene viewport override.** Most specs render at one viewport (the
spec-level `video_viewport_width` / `video_viewport_height`, defaults
1280×720). When one scene needs a wider canvas (a dense plan-review page with
a map + side metrics + a table that wraps awkwardly at 1280), set
`viewport: {width, height}` on that scene only — it appears in the spec
example at the top of this file. The recorder calls `page.set_viewport_size()`
before the scene's goto and restores the spec-level default after
`final_hold_ms`. Important constraint: **the recorded mp4 frame size stays
fixed at the spec-level resolution** — Playwright's `record_video_size` is
set at context creation and cannot change mid-stream. Per-scene viewport
changes the page LAYOUT (CSS pixels) only; the wider logical viewport is
letterboxed into the fixed mp4 frame. This is genuinely useful — the layout
breathes — but don't expect the dense scene to be sharper in the video. For
per-scene resolution, use multiple render passes + ffmpeg concat (out of
scope for normal authoring).

**Create-and-carry-through flows.** A scene may omit its `url` to *continue on the
page the previous scene's actions navigated to*. This is how a narrative can CREATE
an entity in one scene (e.g. click "Create plan" → the app routes to the new
record's page) and operate on it in later scenes whose URL can't be known ahead of
time. Give scene 1 a `url` (the entry point); leave `url` empty on continue-scenes
and drive them with `actions` (use a `goto` action to jump to a known static page
like a workspace, and click-by-name to return to the created record). In a
continue-scene a leading `goto` IS meaningful (it's a deliberate page change, not
a redundancy) — the strip rule only fires when both `url:` AND a leading `goto` to
the same path are set.

### Pacing

The default `fast` preset uses a short hold, a smooth eased scroll over
tall pages, then a short final hold. The scroll motion is what keeps
"fast" from feeling fast-forwarded — viewers register movement as natural
pace rather than a freeze-frame jump-cut.

| Pace   | Initial hold | Scroll speed | Final hold | Min per scene |
| ------ | ------------ | ------------ | ---------- | ------------- |
| fast   | 0.8s         | 1200 px/s    | 0.5s       | 2.5s          |
| medium | 1.5s         | 600 px/s     | 1.0s       | 4.0s          |
| slow   | 2.5s         | 300 px/s     | 1.5s       | 6.0s          |

Per-scene override: set `video_hold_seconds: N` on a scene to skip the
scroll for that scene and dwell a fixed N seconds instead. Use for key
moments where the viewer should sit with one screen.

### Run

Export the live browse cookies so the recorder inherits the auth you
already established during capture, then invoke the script:

```bash
$B cookies > /tmp/walkthrough-cookies-<name>.json

REC=""
for P in \
  ~/emdash-projects/canopy/scripts/walkthrough/record_video.py \
  ~/.claude/plugins/marketplaces/canopy/scripts/walkthrough/record_video.py; do
  [ -f "$P" ] && REC="$P" && break
done
[ -z "$REC" ] && echo "NOT_FOUND" && exit 1

python3 "$REC" \
  --input /tmp/walkthrough-run-data.json \
  --spec docs/walkthroughs/<name>.yaml \
  --output screenshots/walkthroughs/<name>.mp4 \
  --cookies /tmp/walkthrough-cookies-<name>.json
```

Requires `playwright>=1.40` with Chromium installed (`pip install
'playwright>=1.40' && python -m playwright install chromium`, or
`pip install -e '<canopy>[browser]'`) and `ffmpeg` on PATH. The script
exits with a clear error if either is missing.

Report the mp4 path to the user alongside the HTML deck path. The video
is silent by design — narration / captions are expected to be added by
post-processing tooling outside this skill.

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

## Offer to Share

After the deck is verified, **ask once** whether to upload it to canopy-web for
sharing. Don't auto-upload — the user picks per run, and many runs are dev
churn that shouldn't get a share URL.

Prompt the user with the deck path and two options. If they want to share,
invoke `/canopy:walkthrough-share <path>` (the slash command — not bash).
Pass `--public` if they want a shareable link, otherwise leave it private
(dimagi-only). If `screenshots/walkthroughs/<name>.mp4` was also produced,
the user can run `/canopy:walkthrough-share` on that path too — videos are a
separate upload.

If the upload skill fails because the upload token isn't configured, surface
the error verbatim and point the user at `/canopy:walkthrough-share`'s
"First-time setup" section. Don't try to debug auth from inside this skill.

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
