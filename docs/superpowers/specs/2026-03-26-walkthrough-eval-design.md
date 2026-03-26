# Walkthrough Eval Design

**Date:** 2026-03-26
**Status:** APPROVED

## Problem

We build and iterate on the walkthrough skill's scoring prompt, orchestration
logic, and specialist routing — but have no way to measure whether changes
make things better or worse. We need a rerunnable eval suite with fixed inputs,
measurable outputs, and trend tracking.

## Solution

Three components:

1. **Defect creator skill** — Takes a clean HTML page and produces fixture
   variants with calibrated, documented defects. Generates the ground truth.
2. **Eval skill** — Runs the walkthrough against each fixture, compares scores
   to ground truth, computes accuracy metrics.
3. **Fixture structure** — Static HTML pages + walkthrough specs + ground truth
   JSON, stored in `evals/walkthrough/`.

## Architecture

### File Layout

```
plugins/canopy/
├── skills/walkthrough-eval/SKILL.md          — eval runner
├── skills/walkthrough-defect-creator/SKILL.md — fixture generator
├── commands/walkthrough-eval.md              — command wrapper
└── commands/walkthrough-defect-creator.md    — command wrapper

evals/walkthrough/
├── source/                                   — clean source pages
│   └── <name>/
│       └── index.html                        — the good page (copy from website-builder etc.)
├── fixtures/
│   ├── <name>-clean/
│   │   ├── index.html                        — unmodified source page
│   │   ├── spec.yaml                         — walkthrough spec
│   │   └── ground-truth.json                 — expected scores (all 4-5)
│   ├── <name>-bad-content/
│   │   ├── index.html                        — source page with content defects injected
│   │   ├── spec.yaml
│   │   ├── ground-truth.json                 — expected scores + expected detections
│   │   └── defects.json                      — what was changed and why (audit trail)
│   ├── <name>-bad-styling/
│   │   └── ...
│   ├── <name>-bad-demo-readiness/
│   │   └── ...
│   └── <name>-mixed/
│       └── ...
├── eval-history.json
└── eval-runs/
    └── YYYY-MM-DD-vNNN/
        ├── results.json                      — per-fixture scores + aggregate metrics
        └── fixtures/
            └── <fixture-name>/
                ├── sidecar.json              — raw walkthrough JSON output
                └── screenshots/
```

### Component 1: Defect Creator Skill

**Purpose:** Take a clean HTML page and produce fixture variants with known,
documented defects. Each variant targets a specific scoring dimension.

**Invocation:** `/walkthrough-defect-creator <source-name>`

**Input:** A clean page at `evals/walkthrough/source/<name>/index.html`

**Output:** For each defect category, produces:
- `index.html` — the modified page with defects injected
- `defects.json` — manifest of what was changed
- `ground-truth.json` — expected walkthrough scores
- `spec.yaml` — walkthrough spec for the fixture

**Defect categories and injection strategies:**

| Category | Target dimension | What the skill does |
|----------|-----------------|---------------------|
| `bad-content` | Content Quality ≤ 2 | Replace specific product claims with generic placeholder text ("Lorem ipsum", "Your product here"), introduce factual inconsistencies (change numbers to contradict each other), add demo data artifacts ("Unknown Organization", duplicate entries) |
| `bad-styling` | App Page Quality ≤ 2 | Break CSS: remove key media queries, add overlapping z-index issues, kill visual hierarchy (make all text same size/weight), add clashing colors, break spacing |
| `bad-demo-readiness` | Demo Readiness ≤ 2 | Add visible loading spinners, replace real content with "loading..." placeholders, add JavaScript error overlays, insert broken image references, add "TODO" markers |
| `mixed` | Multiple dimensions ≤ 3 | Combine 1-2 defects from each category at moderate severity |

**Defect manifest format (`defects.json`):**

```json
{
  "source": "connect",
  "category": "bad-content",
  "created_at": "2026-03-26T10:00:00Z",
  "defects": [
    {
      "id": "content-1",
      "description": "Replaced hero headline with generic placeholder",
      "dimension": "content",
      "severity": "high",
      "line_range": [15, 15],
      "original": "CommCare Connect: Verified Service Delivery",
      "replacement": "Your Product Name: A Solution For Your Needs"
    },
    {
      "id": "content-2",
      "description": "Changed impact stat to contradict body text",
      "dimension": "content",
      "severity": "medium",
      "line_range": [142, 142],
      "original": "101,000+ health services delivered",
      "replacement": "5,000+ health services delivered"
    }
  ]
}
```

**Ground truth generation:** The skill generates `ground-truth.json` based
on the defects it injected:

```json
{
  "expected_scores": {
    "scene_1": {
      "content": {"min": 1, "max": 2},
      "app_page": {"min": 4, "max": 5},
      "screenshot": {"min": 3, "max": 5},
      "slide": {"min": 3, "max": 5},
      "demo_readiness": {"min": 1, "max": 3}
    }
  },
  "expected_detections": [
    {
      "id": "content-1",
      "description": "generic placeholder text in hero headline",
      "dimension": "content",
      "match_hint": "Your Product Name"
    },
    {
      "id": "content-2",
      "description": "impact stat contradicts body text",
      "dimension": "content",
      "match_hint": "5,000"
    }
  ],
  "expected_routing": {
    "review": true,
    "design_review": false,
    "qa": true
  }
}
```

**Walkthrough spec generation:** The skill creates a `spec.yaml` for each
fixture. All fixtures share the same structure — single persona, one scene
per major page section (hero, features, impact, CTA). The spec's `base_url`
is templated as `http://localhost:{{PORT}}` — the eval skill fills it in at
runtime.

**Workflow:**

1. Read the source page at `evals/walkthrough/source/<name>/index.html`
2. For each defect category:
   a. Copy the source page
   b. Apply defect injections (edit HTML/CSS directly)
   c. Write `defects.json` documenting each change
   d. Generate `ground-truth.json` with expected score ranges
   e. Generate `spec.yaml`
   f. Write all files to `evals/walkthrough/fixtures/<name>-<category>/`
3. Also create the `<name>-clean` fixture (unmodified source + ground truth
   expecting 4-5/5 across all dimensions)
4. Report: "Created {n} fixtures from source '{name}'"

**Regeneration:** Run the skill again after improving the source page. It
overwrites existing fixtures. The defect injection logic is in the skill
prompt — it reads the page, understands the content, and makes targeted,
realistic modifications rather than applying blind string replacements.

### Component 2: Eval Skill

**Purpose:** Run the walkthrough against each fixture, compare scores to
ground truth, compute accuracy metrics, track trends.

**Invocation:**

| Command | Action |
|---------|--------|
| `/walkthrough-eval run` | Run all fixtures |
| `/walkthrough-eval run <fixture>` | Run a single fixture |
| `/walkthrough-eval history` | Show metric trends |
| `/walkthrough-eval compare <r1> <r2>` | Side-by-side comparison |
| `/walkthrough-eval consistency <fixture>` | Run same fixture 3x, measure variance |

**Eval workflow (for `run`):**

For each fixture in `evals/walkthrough/fixtures/`:

1. **Serve the fixture:**
   ```bash
   python3 -m http.server 0 --directory evals/walkthrough/fixtures/<fixture>/ &
   ```
   Parse the port from output.

2. **Prepare the spec:** Copy `spec.yaml`, replace `{{PORT}}` with actual port.
   Write the resolved spec to a temp location the walkthrough skill can read.

3. **Run the walkthrough skill:** Invoke `/walkthrough <resolved-spec>` against
   `localhost:<port>`. The skill runs all scenes, scores on 5 dimensions,
   writes the JSON sidecar.

4. **Kill the server.**

5. **Read the sidecar** and extract per-scene scores + commentary.

6. **Compare against ground truth:**

   **Calibration:** For each scene × dimension, check if the walkthrough's
   score falls within the expected `[min, max]` range. Count hits vs misses.

   **Detection:** For each expected detection in ground truth, search the
   walkthrough's commentary and issues for a match. Use the `match_hint`
   string — if the commentary mentions it, the defect was detected. Count
   found vs missed.

   **Severity accuracy:** For each detected defect, check if the walkthrough
   attributed it to the correct dimension. Count correct vs incorrect.

   **Routing:** If the fixture has `expected_routing`, check what the
   walkthrough's action list recommended (which specialist skills it would
   dispatch to). Compare against expected.

7. **Save results** to `eval-runs/YYYY-MM-DD-vNNN/fixtures/<fixture>/`.

After all fixtures:

8. **Compute aggregate metrics:**

   | Metric | Formula | Weight |
   |--------|---------|--------|
   | Calibration accuracy | scores in range / total scores | 0.35 |
   | Detection rate | defects found / defects planted | 0.30 |
   | Severity accuracy | correct dimension / detected defects | 0.15 |
   | Routing accuracy | correct routing / total routing decisions | 0.20 |
   | **Composite** | weighted average | 1.00 |

9. **Write `results.json`:**
   ```json
   {
     "run_id": "2026-03-26-v001",
     "timestamp": "2026-03-26T10:30:00Z",
     "walkthrough_version": "skill content hash or git SHA",
     "fixtures": {
       "connect-clean": {
         "calibration": {"hits": 5, "total": 5, "accuracy": 1.0},
         "detection": {"found": 0, "planted": 0},
         "details": { ... }
       },
       "connect-bad-content": {
         "calibration": {"hits": 4, "total": 5, "accuracy": 0.8},
         "detection": {"found": 3, "planted": 3, "rate": 1.0},
         "severity": {"correct": 3, "total": 3, "accuracy": 1.0},
         "routing": {"correct": 1, "total": 1, "accuracy": 1.0},
         "details": { ... }
       }
     },
     "aggregate": {
       "calibration": 0.84,
       "detection": 0.85,
       "severity": 0.91,
       "routing": 0.83,
       "composite": 0.85
     }
   }
   ```

10. **Append to `eval-history.json`.**

11. **Report:**
    ```
    Walkthrough Eval — 2026-03-26-v001
    ═══════════════════════════════════════════

    Fixture           Calibr.  Detect.  Severity  Routing
    ─────────────────────────────────────────────────────
    connect-clean      5/5      -        -         -
    connect-bad-cont   4/5      3/3      3/3       1/1
    connect-bad-styl   3/5      2/3      2/2       1/1
    connect-bad-demo   5/5      2/2      2/2       1/1
    connect-mixed      4/5      4/5      3/4       2/3
    ─────────────────────────────────────────────────────
    AGGREGATE          84%      85%      91%       83%

    Composite: 0.85
    vs baseline: +0.07
    Trend: improving (3 consecutive gains)
    ```

**`consistency` mode:** Runs the same fixture 3 times, computes per-dimension
score standard deviation. Reports which dimensions are stable vs noisy.
A well-calibrated prompt should have stddev ≤ 0.5 per dimension.

**`compare` mode:** Loads two runs' `results.json`, shows side-by-side metrics
with deltas. Highlights which fixtures improved or regressed.

**`history` mode:** Reads `eval-history.json`, shows composite trend over time.

### Component 3: Commands

**`commands/walkthrough-eval.md`** — thin wrapper that reads the eval SKILL.md
and follows it. Allowed tools: Read, Bash, Write, Edit, Glob, Grep,
AskUserQuestion, Agent, Skill.

**`commands/walkthrough-defect-creator.md`** — thin wrapper that reads the
defect creator SKILL.md and follows it. Allowed tools: Read, Bash, Write,
Edit, Glob, Grep, AskUserQuestion.

### Feedback loop

The intended workflow:

```
1. Build/improve a website (website-builder or manual)
2. Copy it to evals/walkthrough/source/<name>/
3. Run /walkthrough-defect-creator <name>     → generates fixtures
4. Run /walkthrough-eval run                  → baseline scores
5. Edit the walkthrough skill prompt
6. Run /walkthrough-eval run                  → compare to baseline
7. /walkthrough-eval compare <v001> <v002>    → see what improved/regressed
8. Iterate 5-7 until composite improves
```

When you improve the source website:
```
1. Update evals/walkthrough/source/<name>/index.html
2. Run /walkthrough-defect-creator <name>     → regenerates all fixtures
3. Run /walkthrough-eval run                  → new baseline on better fixtures
```

### Changes Required

1. Create `plugins/canopy/skills/walkthrough-eval/SKILL.md`
2. Create `plugins/canopy/skills/walkthrough-defect-creator/SKILL.md`
3. Create `plugins/canopy/commands/walkthrough-eval.md`
4. Create `plugins/canopy/commands/walkthrough-defect-creator.md`
5. Create `evals/walkthrough/source/` directory structure
6. Copy website-builder Connect page as initial source fixture
7. Run defect creator to generate initial fixtures
8. Bump plugin version
