# Changelog

All notable changes to canopy are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versions track the `VERSION` file and `plugins/canopy/.claude-plugin/plugin.json`,
which are kept in lockstep (every change under `plugins/canopy/` requires a patch
bump — see `.claude/CLAUDE.md`). The project does not tag releases. Pre-history
prior to the entries below was not formally changelogged; this file starts from the
recent, verifiable themes in the git log.

## [0.2.172] - 2026-06-04

### Changed
- **walkthrough recorder: smooth scene transitions + filmable native `<select>`s.** Two fixes to the DDD/walkthrough video recorder, both general (not feature-specific). (1) **Crossfade** — the browser paints a white flash during `page.goto` between scenes, which the continuous recording captured as a jarring blink. The recorder now screenshots the outgoing scene and lays it over the incoming page at max z-index, fading it out once the new page is visually ready (its `load` event, or a safety cap) — so scenes dissolve into each other instead of flashing white. (2) **Filmable dropdowns** — native OS `<select>` popups can't be screen-recorded, so a `select` action used to silently flip the closed widget's value (the viewer never saw the options or that a choice was made). The recorder now renders a synthetic styled dropdown over the select showing every option with the chosen one highlighted, glides the cursor onto it, holds (`select_reveal_dwell_ms`, default 1000ms), then commits and closes. Both behaviours are on by default and gated by `RecorderConfig.crossfade` / `.select_reveal`. `.first` on the select commit keeps a multi-row selector from throwing strict-mode.

## [0.2.171] - 2026-06-04

### Added
- **ddd: lock the narrative on approve — an approved narrative is durable input, not regenerable text.** `UnifiedSpec` gains `narrative_locked` (+ `narrative_locked_at`), stored in the spec file so it travels with the narrative artifact (the whole spec: narrative paragraph + every scene's narrative/show/design_intent/features/actions). The narrative-agreement gate sets the lock on `approve` and clears it on `redraft`; `ddd-spec` and the orchestrator skip regeneration when locked. So you approve the story once, then re-iterate render→judge→converge→upload as many times as you like without ever rewriting it — `redraft` is the single explicit door back to authoring. New CLI: `python -m scripts.ddd.narrative locked|lock|unlock <spec>`. (#137)

## [0.2.169] - 2026-06-04

### Changed
- **visual-judge / ddd-concept-eval: real-but-ugly production data is grounding, not a flaw — only fixtures cap.** v0.2.167's `artifact_kind: product_walkthrough` correctly stopped penalizing real product chrome, but its DATA clause still listed "a raw program slug" as an always-flaw and hardcoded a real program's real name (`ACE-IT-1777407074899-renamed`) as the textbook bad example — so a live product got capped to 2/fail for showing the genuine (if ugly) name of a real record. That conflated two different things. The methodology now distinguishes **fixture/placeholder data that signals an unfinished build** (`test-user`, `Untitled`, lorem, duplicate titles — still a flaw in any mode) from **real-but-ugly production data** (a real entity's real system-assigned identifier, even an auto-generated slug — what the live product actually shows, so under `product_walkthrough` it is grounding like the chrome). When a judge can't tell fixture from real, it now defaults to real and does not deduct. Removes the hardcoded slug example from both skills. Matches the connect-labs precedent (PR #380 → #383): if a judge dings real-but-ugly env data, calibrate the rubric — don't hack a display name for the judge.

## [0.2.167] - 2026-06-04

### Changed
- **visual-judge / ddd-concept-eval: `artifact_kind` makes real product chrome grounding, not a deduction.** A new `context.artifact_kind` field distinguishes `product_walkthrough` (a frame of a real, shipping web app driven through a flow) from `standalone_deliverable` (a slide/figure, the default). In walkthrough mode the surrounding product chrome — nav, sidebar, breadcrumbs, account menu, the app's own buttons — is EXPECTED and grounds the demo as a real product, so it no longer fires the "internal app chrome → max 3" sanity floor and is not listed as a flaw. Test/placeholder DATA (raw primary-key slugs, `test-user`, `Untitled`, lorem) still caps in either mode. `ddd-concept-eval` now passes `artifact_kind: product_walkthrough` for every DDD scene. Motivated by walkthrough judges wrongly penalizing the real-website nav that is the whole point of a live-product demo.

## [Unreleased]

### Changed
- **DDD `ddd-promote` → `ddd-upload`; convergence returns the run PACKAGE URL,
  not a loose artifact link.** The terminal DDD step was named "promote" but it
  has no promotion semantics — it just uploads a converged run's artifacts to
  canopy-web. Renamed the skill/command/script (`scripts.ddd.promote` →
  `scripts.ddd.upload`, `promote()` → `upload_run()`) and the run phase
  (`promoted` → `uploaded`, with `promoted` kept as a read alias for existing
  run_state files). More importantly, `upload_run()` now returns the navigable
  **run package** URL `/ddd/<feature>/<run_id>` — the canopy-web view (PR #77)
  that groups the run's video + deck + narrative + links — instead of the loose
  `/w/<artifact-id>` docs-page link it returned before. Fixes the symptom where
  every converged run handed back a single isolated artifact rather than the
  navigable package.

### Added
- **`/canopy:ddd` infers the narrative when none is passed.** Saying "do DDD
  with the orchestrator" (no explicit `<feature>`) no longer errors or prompts
  for setup — a new `scripts.ddd.resolve_narrative` resolver ranks narratives by
  the newest `.canopy/ddd/runs/*` run, the newest `docs/walkthroughs/*.yaml`
  spec, and a match against the current git branch, then resumes the in-flight
  run (or starts a fresh one) and just proceeds. It only pauses to ask when
  several narratives were touched at once (`confidence: ambiguous`) or there's
  nothing to infer from. Wired into the DDD agent's Bootstrap as step 4.
- **CI gate: docs-sync between engine source paths and SKILL.md** (#117) —
  Structural enforcement of the rule the #115 audit surfaced: engine PRs that
  change user-facing authoring surface MUST update the teaching SKILL.md in
  the same PR, or carry a deliberate opt-out marker. Of the 14 canopy PRs
  shipped on 2026-06-01, only #108, #111, #113, and #115 explicitly touched
  SKILL.md when they should have — #100, #101, #102, #105, #112, and #114 all
  shipped new spec-author surface (`Scene.url`, `must_succeed`, prefix syntax,
  snapshot flags, `scroll_to` cursor glide, `Scene.viewport`) without updating
  the docs, costing a meta-audit PR (#115) and a follow-up (#116) to backfill.
  The new gate (`.github/workflows/docs-sync.yml` runs the testable Python
  script at `.github/scripts/docs_sync_check.py`) maps four trigger source
  paths to their required teaching docs:
  - `scripts/ddd/schemas/models.py` → `ddd-spec/SKILL.md` + `walkthrough/SKILL.md`
  - `scripts/walkthrough/_lib/recorder.py` → `ddd-spec/SKILL.md` + `walkthrough/SKILL.md`
  - `scripts/walkthrough/record_video.py` → `ddd-run/SKILL.md`
  - `plugins/canopy/skills/ddd-concept-eval/rubric.yaml` → `ddd-concept-eval/SKILL.md`

  When a PR touches a trigger key but skips any required value, the gate
  fails with a structured message that names both the trigger and the
  missing docs, cites the prior gap PRs as rationale, and teaches the
  opt-out marker syntax. Opt-out: a line `Docs-not-needed: <reason>` in the
  PR body — for genuine engine-internal changes (refactor, perf, bug fix
  with no authoring contract change), the gate passes with a notice logging
  the reason. 24 unit tests cover the pure-logic path plus a sanity check
  that every trigger/required-doc path actually exists in the repo (renames
  would otherwise silently disable the gate). No behavior change for PRs
  that don't touch trigger paths — fast no-op silent pass.
- **Pre-commit hook: auto-regen DDD JSON schemas from `models.py`** (#118) —
  The Pydantic models in `scripts/ddd/schemas/models.py` are the source of
  truth; the committed schemas at `scripts/ddd/schemas/json/*.json` are
  downstream artifacts consumed by `scripts/ddd/validate.py` and external
  tools. They're supposed to stay in lockstep, but the gap between "edit
  models.py and commit" and "CI catches the drift" is wide enough to bite
  real work: `DrawAction` (added in #104) was missing from `UnifiedSpec.json`
  for two days until someone re-ran the regen by hand during #108. The new
  hook (`.pre-commit-config.yaml`, repo-local) fires only when `models.py`
  is staged, runs `dump_json_schemas`, and uses pre-commit's standard
  modify-then-fail pattern: if the regenerated JSON differs from what's
  committed, pre-commit blocks the commit with "files were modified by this
  hook" and the developer runs `git add scripts/ddd/schemas/json/` to fold
  the regen into the same commit. The existing
  `tests/ddd/test_validate.py::test_committed_json_schemas_match_generated`
  test still catches anyone who skipped `pre-commit install` or pushed via
  the GitHub web UI — belt and braces. No new Python dependencies; no
  behavior change for developers who haven't run `pre-commit install` (the
  config is just dormant).

### Changed
- **DDD authoring docs — close 4 secondary gaps from #115's audit** (0.2.156) —
  Follow-up to #115. The PR #115 audit pass closed six high-leverage authoring
  gaps but explicitly scoped out four smaller ones for follow-up. They're all
  real and worth closing now while the audit context is fresh. Docs-only across
  two SKILL.md files; no engine behavior changed.
  - `plugins/canopy/skills/ddd-spec/SKILL.md` + `plugins/canopy/skills/walkthrough/SKILL.md`:
    **`Action.draw` generalized beyond Mapbox** — `tool`-field coordinate-click
    pattern documented as applying to ANY tiny canvas-control surface
    (Mapbox GL Draw, Leaflet.draw, MapLibre, custom React-Konva / SVG drawing
    surfaces), not just Mapbox. The existing Mapbox-only example was misleading:
    authors using Leaflet or custom canvas tools wouldn't discover from the
    docs that the same `kind: draw` recipe applies to their surface.
  - `plugins/canopy/skills/ddd-spec/SKILL.md` + `plugins/canopy/skills/walkthrough/SKILL.md`:
    **`click_menu` verb explained** — the verb appeared in the action-verb list
    with zero example. Now documents the "second click in an open-menu → pick-item
    sequence" intent, the shorter `menu_click_settle_ms`, and the explicit "don't
    use it for the click that OPENS the menu" anti-pattern. Authors were either
    falling back to verbose two-`click` sequences or stumbling onto it from
    `_lib/recorder.py` source.
  - `plugins/canopy/skills/ddd-spec/SKILL.md` + `plugins/canopy/skills/walkthrough/SKILL.md`:
    **`Action.note:` documented as a persistent artifact, not a comment** —
    `note:` ships into the run report + recorder per-action log + judge
    context, but the docs never said so. Authors were using it as throwaway
    YAML-comment-style annotations ("click submit") that add noise without
    signal. Now explicitly: notes ship; write them for disambiguation,
    ordering rationale, or downstream-trigger context.
  - `plugins/canopy/skills/walkthrough/SKILL.md`: **`scene_index` preservation
    across `--scene` filter for hand-edited sidecar JSON** — the existing
    `--scene` docs covered the rendered deck but didn't say that when authors
    hand-edit `/tmp/walkthrough-run-data.json` to add or correct scores, the
    `scene_index` field MUST stay as the original spec index, not flatten to
    1-of-N within the filtered set. Flattening breaks all cross-run analytics
    that key on the original index.

- **DDD authoring docs roundup — lock in PR #100–#114 best practices** (0.2.155) —
  Six concrete authoring patterns shipped between #100 and #114 but never made it
  into the skill docs, so the next agent doing DDD on a fresh feature would
  reinvent traps already solved. Docs-only; no engine behavior changed; existing
  specs continue to validate and record identically.
  - `plugins/canopy/skills/ddd-spec/SKILL.md`: new **Authoring checklist** near
    the top (scannable one-liners with pointers to the deeper sections); inside
    Step 4 (scene-start authoring), four new in-place sections — **Target
    resolution syntax** (prefix matrix: `css:`/`testid:`/`aria:`/`role:`/`text:`
    with the routing call each maps to and "when to use" guidance), **`must_succeed:
    true` for critical actions** (the form-submit / navigation that, if it silently
    misses, makes every later scene grade against the wrong page state),
    **Don't `wait_for` on a transient intermediate state** (the `Creating 10 plan`
    race; wait only on TERMINAL states + cite the `microplans-10-wards` example),
    and **Per-scene viewport override** (the `viewport: {width, height}` field
    from #114 — including the mp4-frame-size constraint authors need to know about
    so they don't expect higher-resolution video from it).
  - `plugins/canopy/skills/walkthrough/SKILL.md`: mirror of the same four sections
    in the interactive-recording area, so the walkthrough author hits the same
    guidance without needing to read the DDD spec skill.
  - `plugins/canopy/skills/ddd-run/SKILL.md`: new **Recording CLI flag matrix**
    in Step 2 — the canonical default flag set the orchestrator should pass to
    `record_video.py` (`--snapshots` always, `--report` always, `--skip-empty-scenes`
    + `--skip-same-url` for typical specs, `--cookies` for session auth), with
    per-flag "when to pass it" rationale. Also a "scan `run-report.json` for
    failed `must_succeed` actions before letting the judges run" note tying back
    to the spec-side `must_succeed: true` docs.

### Added
- **Per-scene viewport override (`Scene.viewport`)** (0.2.154) — `video_viewport_width` /
  `video_viewport_height` work at the spec top level but you couldn't bump one
  dense scene without inflating the whole recording. DDD agent on
  `microplans-10-wards-fullrun-2026-06-02-001` wanted scene 4 (Mapbox plan-review
  with a wide inspector panel) at 1440×900 without bumping the other five scenes.
  Now `Scene.viewport: { width: int, height: int }` (optional) does exactly
  that: `Recorder.run_scene` calls `page.set_viewport_size` BEFORE the goto so
  the freshly-loaded page lays out at the requested size from the first paint,
  then restores the spec-level default after `final_hold_ms`. The mp4 frame
  size stays fixed (Playwright's `record_video_size` is set at context creation
  and cannot change mid-stream) — the recording canvas re-fits / letterboxes
  the larger logical viewport into the spec-level frame. No-op fast-path when
  the requested viewport matches the current. Authored example:
  ```yaml
  scenes:
    - title: "Dana drills into the plan map"
      url: "/microplans/program/133/plan/3536/review/"
      viewport: { width: 1440, height: 900 }  # this scene needs more room
      actions: ...
  ```

### Fixed
- **Scene-transition gray-viewport window after WebGL/Mapbox scenes** (0.2.154) —
  frame-sampling `microplans-10-wards-fullrun-2026-06-02-001/iter1_clip.mp4` from
  t=102s to t=108s showed ~7s of solid gray while the recorder navigated from a
  Mapbox-heavy plan-review page to the glossary page. Root cause: leaving a
  WebGL-heavy page, residual GL-teardown telemetry + tile-fetch network activity
  from the torn-down page stalls Playwright's lifecycle tracking, so the `load`
  event signal can hang for the full `load_settle_timeout_ms` (8s) while
  Chromium hasn't painted the new page's first frame yet — pure gray for the
  viewer. The recorder's per-scene goto already knew (via `skip_settle=True`)
  that the next action was `wait_for` and would do its own polling, so it
  already skipped the trailing `goto_settle_ms` blind hold. Now `goto_and_settle`
  also uses `wait_until="commit"` (return as soon as the navigation request is
  committed) and skips the `wait_for_load_state("load")` block entirely on that
  same path — the wait_for action that's about to fire IS the settle, much more
  accurate than guessing at `load` event timing. Back-compat: `skip_settle=False`
  preserves the original `domcontentloaded` + `load` + `goto_settle_ms` flow for
  every non-wait_for first action.
- **WebGL/Mapbox screenshot timeouts now settle + retry once** (0.2.154) — the
  recurring SwiftShader-headless bug (`reference_browse_webgl_swiftshader`):
  `Page.captureScreenshot` hangs on canvas-heavy pages in headless Chromium.
  The DDD agent on `microplans-10-wards-fullrun-2026-06-02-001` worked around it
  manually by re-capturing the failing scene in a separate `playwright.sync_api`
  session with an explicit 8-10s sleep before `page.screenshot()`. That's now
  built into `Recorder.take_snapshot`: first attempt uses `timeout=10000`; on
  timeout, `wait_for_timeout(8000)` to give the GL context time to finish
  whatever frame it was mid-render on, then one retry at `timeout=20000`. If
  the retry also fails, the recorder writes the text dump regardless (so
  visual-judge has at least one input per scene) and logs a one-line warning —
  never raises, never aborts the multi-scene run. One settle + one retry is
  the contract — no infinite retry loop.

### Changed
- **DDD concept-eval rubric grows a `visual_polish` dimension** (0.2.153) — the
  prior 5-dim rubric (`concept_clarity`, `design_soundness`, `why_groundedness`,
  `claim_reality_coherence`, `motion_friction`) had no place to land pure-visual
  failures. `design_soundness`'s anchors and deduction rules were about
  INTERACTION coherence — dead ends, contradictory affordances, unlabeled
  actions — so demonstrably ugly UI (misaligned elements, garish color,
  inconsistent button styles, bad typography, crowded layouts) shipped through
  the judge with passing scores because the rubric never asked.
  - New `visual_polish` dim (weight 0.15): Tough Judge anchors from 5
    ("shippable as marketing material") → 1 ("unfinished or amateur"), with 7
    deduction rules covering alignment, contrast, hierarchy, density, control
    consistency, overflow, and semantic color usage. Counts toward the
    weakest-link `overall_score` like every other gating dim.
  - `design_soundness` weight trimmed 0.25 → 0.20; label clarified to "Design
    Soundness (Interaction Coherence)" to make the scope split explicit.
  - `claim_reality_coherence` weight trimmed 0.15 → 0.10 (still advisory).
  - `motion_friction` weight trimmed 0.20 → 0.15. Weights still sum to 1.0.
  - Routing: `visual_polish` findings → PRODUCT by default (visual fixes are
    template/CSS changes); rare CONCEPT route when the rendered chrome reveals
    an information-architecture problem.
  - `tests/skills/test_ddd_concept_eval_structure.py` updated to expect 6 dims
    including `visual_polish`. Full canopy suite green (1567 passed).
- **Scene-transition dead-air: cursor follows `scroll_to`, no-nav scenes skip
  `initial_hold_ms`** (0.2.152) — frame-sampling `microplans-10-wards` v0.2.151
  (https://canopy-web-ujpz2cuyxq-uc.a.run.app/w/0212e21b-238c-422d-8c32-62289f487f4c)
  after PR #111 landed: scene 1 dropped from ~12s to ~5s, but viewers still saw
  ~5s of "static workspace, nothing happening" between the page load (t=2s) and
  the first visible motion (t=7s). Two structural causes PR #111 didn't address.
  Both fixes are additive — existing specs record identically, just faster.
  - **`scroll_to` glides the cursor onto the target.** Mirrors the
    resolve → glide → act shape every other primitive (`click_text`,
    `fill_field`, `select_option`, `hover`) already uses. A common pattern is
    `scroll_to` defensively before a click; when the element is already in
    view the page may not move at all but the cursor still visibly arrives
    on what's about to be clicked, so the viewer never sees a frozen
    `scroll_settle_ms` of nothing. After the smooth-scroll, the recorder
    re-measures the locator (the smooth-scroll moved it) and short-glides
    the cursor to follow it to its new viewport position — same re-measure
    pattern `click_text` uses to land on a settled element.
  - **`initial_hold_ms` skipped on no-nav scenes.** PR #111 skipped the hold
    when the first action was `wait_for` (the wait_for IS the settle). This
    extends the skip: when `goto_for_scene` returns `None` (stay-on-page
    scene, either via `SkipSameUrlRecorder` or a scene authored without
    `url:`), there's no page-load transition to settle for. The previous
    scene's `final_hold_ms` already provided any transition pause. So the
    full skip condition is now `url is not None and first_action != wait_for`.
  - 11 new tests under `tests/walkthrough/` —
    `test_scrollto_glides_cursor.py` (five cases covering pre-scroll glide
    centre + steps, move-before-evaluate ordering, post-scroll re-measure
    & re-glide with `cursor_steps_short`, detached-locator no-crash, and
    unresolved-target back-compat) and `test_initial_hold_skip_no_nav.py`
    (six cases pinning the new no-nav skip vs PR #111's existing wait_for
    skip, including the stacked condition, empty-actions edge case, and a
    "no nav means no goto at all" sanity check).

### Fixed
- **Scene-start dead-air: redundant goto + blind holds** (0.2.151) — frame-sampling
  the latest `microplans-10-wards` recording found ~7s of preventable stillness at
  the top of every scene. Three additive recorder fixes (every existing spec keeps
  recording — they just record faster):
  - **Redundant leading `goto` stripped in `build_scenes_from_spec`.** PR #100
    introduced `Scene.url` as the declarative entry point — the orchestrator's
    `run_scene` now navigates to `scene.url` before running actions. But existing
    specs still lead with `{kind: goto, target: <same-url>}` (the pre-#100 entry
    pattern), so the recorder navigated twice — a ~2.5s reload right after the
    title card. When the first action is `goto` and its absolutized target matches
    the resolved `scene.url`, it's now stripped from the action list with a printed
    notice. Non-leading gotos and gotos to a different URL (intentional
    reload-then-elsewhere) are preserved.
  - **`initial_hold_ms` skipped when first action is `wait_for`.** `wait_for` IS
    the settle (polls until a known page state appears) — the default 800-2500ms
    blind hold on top of it is pure dead air. The orchestrator now inspects the
    first action and skips `initial_hold_ms` when it's `wait_for`. Every other
    first-action kind keeps the existing behavior (back-compat for static-scene
    paths and click-first scenes that need the page a moment to render before the
    cursor moves).
  - **`goto_settle_ms` skipped when first action is `wait_for`.** Same logic for
    `goto_and_settle`'s 600-2000ms blind tail — when a `wait_for` is about to run,
    the recorder skips the trailing pause and lets the `wait_for` be the settle.
    Threaded via a `skip_settle=` kwarg; default False keeps any external caller
    bit-identical.
  - Frame breakdown of scene 1 of the original clip (12s):
    `1.25s` real labs page load (TLS + TTFB + DOM parse) — unavoidable.
    `1.2s` `goto_settle_ms`, `1.5s` `initial_hold_ms`, `2.5s` redundant goto
    reload, `2.0s` spec's `hold seconds: 2.0` over-framing — 7.2s preventable.
    `1.5s` scroll glide, `1.0s` hold, `1.0s` `final_hold_ms` — legit. The
    framework changes recover the four blind-hold seconds at the top of every
    scene; the per-spec `hold seconds: 2.0` over-framing is now redundant with
    the leading `wait_for` already settling the page.
  - 13 new tests under `tests/walkthrough/` —
    `test_redundant_goto_dropped.py` (six cases covering match-drops,
    different-url-preserves, no-url-inferred-from-goto, non-leading goto,
    absolute-matches-relative, action-empty no-crash) and
    `test_initial_hold_skip_on_waitfor.py` (sentinel-config approach: scene-aware
    timeouts assert which blind hold fired, covering `scroll_to`/`press`/`wait_for`
    leads, empty-actions back-compat, `final_hold_ms` independence, no-url path).

### Changed
- **`ddd-spec` and `walkthrough` skill docs teach `url:`, not `goto`** (0.2.151) —
  the framework fix above is necessary because the skills themselves taught the
  bad pattern: every action-authoring example lead with `kind: scroll_to`, never
  with `url:` or `wait_for`, and never called out the duplicate-goto trap. So
  every spec authored from these skills shipped the bug. Now both skills lead the
  scene-authoring example with `url:` + `wait_for`, add an explicit anti-pattern
  callout for `url:` + leading-`goto` to the same path, recommend `wait_for
  seconds: N` over `hold seconds: N` for long bulk operations, and document the
  continue-scene pattern (omit `url:` to stay on the previous scene's ending
  page). The SCHEMA is unchanged — old specs still validate; new specs are taught
  the cleaner pattern.

### Added
- **Companion links on the walkthrough viewer** (0.2.150) — an uploaded
  walkthrough can carry typed companion links the canopy-web `/w/<id>` viewer
  renders: `narrative` (back to the story that generated it), `companion`
  (the sibling still-frame deck ↔ video), and `reference` (the app pages the
  demo visited, clickable + live). `walkthrough-share/upload.py` gains
  `--narrative-url`, `--companion-url`, `--link "Label::url"` (repeatable),
  and `--spec` (derives one reference link per scene `url`, deduped).
  `/canopy:ddd-run` attaches them automatically when it uploads each
  iteration's clip — pulling the narrative-review URL the
  `/canopy:ddd-narrative-review` gate now stamps on
  `RunState.narrative_review_url`. Requires the companion canopy-web change
  (the `links` field on the Walkthrough model + viewer panels).
- **`wait_for` per-action `seconds:` timeout + `--skip-empty-scenes`** (0.2.148) —
  two opt-in recorder knobs that together remove ~130s of dead-space from a
  238s microplans-10-wards hero clip. Both ADDITIVE — every existing spec
  records identically without changes.
  - ``WaitForAction.seconds`` is now a per-action timeout override. The
    recorder's default ``wait_for`` timeout is
    ``RecorderConfig.wait_for_timeout_ms`` (12s). When an author knows a
    particular condition might take longer (an SSE bulk-create stream that
    runs 30-90s), the spec can say
    ``{kind: wait_for, target: "Created 10 of 10 plans", seconds: 120}`` —
    the recorder exits the wait the instant the text appears (typically
    30-55s for the bulk-create case), instead of holding blindly. Before:
    authors padded with ``wait_for`` (12s default) → fixed ``hold seconds:
    90`` guarantee, paying the worst-case dead-air on every clip. Frame-
    sampling the latest microplans-10-wards recording every 5s found a
    fully-painted success card frozen from ~55s to ~155s — exactly the
    `wait_for` + blind-hold pattern. Now spec authors say what they
    actually mean: "wait up to N seconds, exit early on match." The schema
    is strict: non-numeric ``seconds`` (e.g. ``"fast"``) fails Pydantic
    validation; negative values floor at 0; ``None`` (default) preserves
    the existing 12s recorder-config default.
  - ``record_video.py --skip-empty-scenes`` — when set, scenes with
    ``len(actions) == 0`` are dropped from the recording loop entirely.
    The mp4 then skips them; the deck still shows them as title-card
    slides built from spec.scenes independently, so the narrative
    survives. Mirrors PR #105's ``--snapshot-empty-scenes`` (also default
    False — back-compat). Same frame-sampling found a 30s static window
    from 200s-240s where scenes 6-11 of microplans-10-wards (no actions)
    held ``min_hold_ms`` on the previous scene's glossary URL — zero
    informational content for 30 of the 238 seconds. The new flag drops
    those frames; the deck-as-title-cards path keeps the narrative.
    Filter runs AFTER ``build_scenes_from_spec`` so surviving scenes
    retain their 1-based ORIGINAL spec ``scene_index`` (matches snapshot
    + ActionResult tagging). Extracted as a tiny pure helper
    (``filter_empty_scenes``) so the test suite pins the contract without
    spinning a browser.
  - 24 new tests under ``tests/walkthrough/`` —
    ``test_waitfor_seconds_override.py`` (Pydantic accepts/rejects, the
    primitive forwards to ``wait_for_target`` as int ms, the dispatcher
    routes ``action["seconds"]`` through, custom ``RecorderConfig`` default
    respected, fractional seconds coerce to int ms, negative floors to 0)
    and ``test_skip_empty_scenes.py`` (``_is_empty_scene`` for empty /
    missing / None ``actions``, ``filter_empty_scenes`` preserves order +
    ``scene_index``, microplans-10-wards back-half shape, composition with
    PR #105's per-scene snapshot gate, back-compat when flag is omitted).
    JSON schemas regenerated via ``dump_json_schemas`` —
    ``UnifiedSpec.json`` now includes ``WaitForAction.seconds`` (also
    backfills the previously-missing ``DrawAction`` defs).

- **Per-scene snapshots + `scene_index`-tagged action results** (0.2.146) —
  three small recorder-framework gaps the DDD orchestrator hit running
  ``microplans-10-wards`` are closed so the full DDD loop runs without
  side-script workarounds.
  - ``record_video.py --snapshots <dir>`` — captures one ``scene_<N>.png``
    (full-page) + one ``scene_<N>_page_text.json`` (``document.body.innerText``
    + url + title) per scene at the **steady-state moment** — between the
    action loop and ``final_hold_ms``, after every post-action settle has
    fired. That's the same surface ``canopy:walkthrough`` eval + ``ddd-
    concept-eval`` need to dual-judge a recording; the DDD agent used to
    write a side script (``/tmp/capture_scenes.py``) to fill the gap. New
    ``Recorder.take_snapshot`` is an overridable hook so subclasses can
    switch to viewport-only, write to S3, or grab extra artifacts (HAR,
    ARIA tree) without re-implementing the steady-state gating.
    ``--snapshot-empty-scenes`` toggles in narrative-only scenes (default:
    skip — there's nothing the cursor could change between init and final).
    Filenames use the **1-based ORIGINAL spec index** so a ``--scene 3``
    partial run produces ``scene_3.png``, not ``scene_1.png`` — matches the
    deck's scene numbering + the actionability-eval scene_index field.
  - ``ActionResult.scene_index`` is now populated (was always ``None``).
    The orchestrator's ``run_scene`` stamps the 1-based original spec index
    onto each result via ``dataclasses.replace`` (the dataclass is frozen).
    ``execute_action`` stays scene-agnostic — the dispatcher doesn't need
    to know which scene it's serving — while every result in ``RunReport``
    carries its source scene for downstream grouping. ``RunReport.to_json``
    serialises the field so external tools see it.
  - ``_render_stars`` in ``generate_presentation.py`` accepts float scores
    (the judge schema's ``ai_evaluation.score`` is a float — 4.5, 5.0). The
    star count rounds to the nearest int while the numeric tail
    (``4.5/5``) keeps the underlying float so half-star precision isn't
    lost. Defensive: ``max_score`` is coerced too in case a future
    contributor emits ``5.0``. The previous ``"★" * score`` threw
    ``TypeError`` whenever the judge produced a half-step score, blocking
    deck generation on real DDD runs.
  - 23 new tests under ``tests/walkthrough/`` —
    ``test_record_video_snapshots.py`` (PNG + JSON contract, original-spec-
    index naming, action-empty gating, lazy dir creation, fallback chain),
    ``test_action_result_scene_index.py`` (multi-scene tagging, partial-
    run index preservation, kwarg-over-dict override, JSON round-trip,
    direct-dispatcher default), ``test_render_stars_accepts_float.py``
    (4.5 + 5.0 don't raise, integer scores unchanged, float ``max_score``
    tolerated). Existing ``Recorder`` / ``RunReport`` tests unchanged.

### Changed
- **Recorder delegates target resolution + clicks to Playwright locators** (0.2.143) —
  the previous resolver shipped a hand-rolled ``_box_center`` JS that scanned the
  DOM ranking actionable-vs-text pools, a polling ``_glide_to`` deadline that
  re-implemented ``Locator.wait_for(state="visible")``, and a
  ``page.mouse.click(x, y)`` coordinate click that bypassed Playwright's
  actionability checks (visible, stable, receives events, enabled, not
  detached). Net effect: a less-reliable clone of a thing Playwright already
  provides correctly. Now the prefix syntax maps directly to ``get_by_*``:
  - ``css:#x`` → ``page.locator("#x")``
  - ``testid:foo`` → ``page.get_by_test_id("foo")``
  - ``aria:Foo`` → ``page.get_by_label("Foo", exact=False)``  (was a CSS
    ``[aria-label*=...]`` substring match that missed ``aria-labelledby`` and
    ``<label for>`` associations; now uses Playwright's accessible-name
    semantics)
  - ``role:button`` / ``role:button:Sign in`` → ``page.get_by_role(...)``
  - ``text:Foo`` → ``page.get_by_text("Foo")``
  Bare targets use a tightened heuristic — ``+ Bulk paste list`` used to read
  as CSS (leading ``+``) and threw on the invalid selector, silently breaking
  the whole microplans-10-wards scene-2 cascade. Now a leading combinator is
  text unless followed by an identifier-shaped char. The auto path also falls
  through from CSS-attempt → text-engine on miss, so a heuristic
  mis-classification is recoverable. ``click_text`` / ``fill_field`` /
  ``select_option`` / ``hover`` / ``scroll_to`` all call ``Locator.click``,
  ``Locator.fill`` + ``Locator.type``, ``Locator.select_option``,
  ``Locator.hover``, ``Locator.scroll_into_view_if_needed`` — full
  actionability checks intact, cursor still glides visually via ``slow_move``.
  E2E vs origin/main on microplans-10-wards: 245 s footage (was 240 s, +2 %
  for the genuine actionability waits — silent failures no longer hide the
  real time cost), 61/62 actions ok, same transient ``Creating 10 plan``
  timeout that's a UI race not a recorder bug. ``tests/walkthrough/
  test_targets.py`` rewrites the dispatch tests against a ``FakePage`` that
  records which Playwright API each prefix routes to.

### Added
- **Discriminated `Action` union — strict per-kind field validation** (0.2.142) —
  the flat `Action` Pydantic model accepted any of `target / value / seconds /
  note / must_succeed` for every verb, so a spec that wrote `{kind: type,
  target: "Buy"}` (the spec author meant `click`, not `type`) used to validate
  clean and silently no-op at recording time. Now `Action` is a Pydantic
  discriminated union with one strict subclass per verb — `GotoAction(target)`,
  `ClickAction(target)`, `FillAction(target, value)`, `SelectAction(target,
  value)`, `TypeAction(value)`, `PressAction(value="Enter")`, `HoverAction(
  target, seconds?)`, `ScrollToAction(target)`, `ScrollAction(value="bottom")`,
  `WaitForAction(target)`, `HoldAction(seconds)`, `ClickMenuAction(target)` —
  each with `extra="forbid"`. Wrong field on a verb is a loud `ValidationError`
  naming the field and the action subclass. `note` and `must_succeed` are
  shared on the base class so every kind keeps both. Surveyed 38 real specs
  across canopy / connect-labs / ace-web / canopy-web — every action shape
  already matches; zero migration required. Adds 20 new `tests/walkthrough/
  test_action_discriminated_union.py` tests pinning per-kind field accept/
  reject rules; existing `test_action_kinds_single_source.py` updated to
  guard the new `ACTION_CLASSES` tuple. JSON Schema regenerated.
- **Per-scene `url` field on the spec schema** (0.2.142) — `Scene.url:
  str | None = None` promotes a scene's starting URL from "inferred from the
  first `goto` action" to an explicit, declarative authoring affordance.
  `record_video.py` already reads this field (added in 0.2.141 ahead of the
  schema). Resolution order in the recorder is now (1) explicit `Scene.url`,
  (2) first `goto` action, (3) captured slide URL from `--input`, (4) `None`
  (stay on previous URL). Backward-compat: existing specs that don't set
  `url` keep validating and recording identically.
- **Recorder primitives refactor — extensible by hook, not by fork** (0.2.141) —
  the per-scene loop, target resolution, timing, and action results are now four
  small modules under `scripts/walkthrough/_lib/` instead of one 405-line file
  plus a monolithic `record_video.main()`. The motivating bug: the
  microplans-10-wards recording needed "skip nav when URL hasn't changed
  between scenes" (so scene 2's resolved table survives into scene 3) and the
  only way to get it was to hand-write a 121-line replacement script that
  re-implemented browser bootstrap, cookie loading, scene iteration, and ffmpeg
  conversion to add a single 4-line behaviour change. Now:
  - `_lib/targets.py` — one `resolve_target(page, target)` and one
    `looks_like_selector()` heuristic, used by every primitive. New explicit
    prefix syntax: `text:`, `css:`, `testid:`, `aria:`, `role:`. Bare targets
    keep working via heuristic (CSS-shaped → selector engine; English → text
    ranking). The previous "wait_for runs page.wait_for_selector on a
    plain-text target and stacks a 12 s hang before the text fallback" bug
    is gone for good (and is covered by a unit test).
  - `_lib/config.py` — every timing constant is a field on a frozen
    `RecorderConfig` dataclass with `fast`/`medium`/`slow` presets. Spec
    authors override any subset via `video_recorder_config: { typing_delay_ms: 20 }`.
    Unknown keys are ignored (forward-compat for newer recorders).
  - `_lib/results.py` — `execute_action` now returns an `ActionResult` with a
    tagged `error_kind` (`target_not_found` / `timeout` / `unknown_kind` /
    `playwright`). `RunReport` accumulates them and the orchestrator prints
    `"62 actions: 61 ok, 1 failed"` plus the failure list at the end of every
    run, so silent fails stop hiding (an action like
    `scroll_to("Plan config")` against a page that no longer has that text
    used to look identical to success in the video; now it shows up in
    `--report report.json` as `error_kind: target_not_found`). Per-action
    `must_succeed: true` raises `ActionAssertError` instead of swallowing.
  - `_lib/orchestrator.py` — `Recorder` class with five overridable hooks
    (`goto_for_scene`, `before_scene`, `after_scene`, `before_action`,
    `after_action`). The skip-nav case is now a 7-line subclass
    `SkipSameUrlRecorder` you opt into with `--skip-same-url`. Custom
    instrumentation (screenshot-on-fail, headed-debug, side-by-side) ships
    as another small subclass — no more orchestrator forks.
  - `record_video.py` — slim CLI over the Recorder. `--input` (the
    walkthrough-run-data.json from `canopy:walkthrough`) is now optional;
    when absent, the YAML spec is the only source of truth for scenes. New
    `--skip-same-url` and `--report <path>` flags.
  - Single `ACTION_KINDS` source in `scripts/ddd/schemas/models.py`. The
    recorder imports it; a guard test fails if the Pydantic `Literal` and the
    tuple ever drift.
  - 46 new unit tests under `tests/walkthrough/` covering target prefixes,
    the heuristic, RecorderConfig presets/overrides, RunReport summaries,
    and the dispatcher's verb table + `must_succeed` behaviour.
  - Backward-compatible: existing specs (no prefixes, no
    `video_recorder_config`, no `must_succeed`) record the same as before
    (verified end-to-end against `microplans-10-wards`: 10 plans created in
    Madobi LGA, 240 s of footage, identical visual pacing).
- **Recorder gains `select` action verb** (0.2.138) — for native `<select>` controls (which `click` cannot reliably open across platforms). `value` is the option's `value` attribute / 0-based-index-as-digit-string / visible label — recorder tries each in order. Adds `select_option()` helper in `scripts/walkthrough/_lib/recorder.py` that uses Playwright's `locator.select_option`. Action enum in `scripts/ddd/schemas/models.py:Action` extended; `scripts/ddd/schemas/json/UnifiedSpec.json` regenerated. SKILL docs for `ddd-spec` and `walkthrough` updated.
- **DDD auto-uploads per-iteration deck/clip to canopy-web** (0.2.135) — `/canopy:ddd-run` Step 2b (new, between render and judge dispatch) generates the iteration's HTML deck, uploads it via `/canopy:walkthrough-share`, and stamps the hosted URL onto `state.iteration_decks[<iteration>]`. Same for the optional MP4 clip → `state.iteration_clips[<iteration>]`. Deck generator now emits `id="scene-<N>"` anchors on every scene slide (original spec index, stable across partial/full runs), so consumers deep-link with `<DECK_URL>#scene-<N>`. Step 5 report banner prints the hosted URLs inline and decorates each finding with its scene deep-link. The `agents/ddd.md` artifact-link contract now reads URLs from run_state directly — surfaced findings never do a one-off manual upload. On upload failure: log to `<run_dir>/upload-errors.md`, fall through to verbal description, never `file://`. Closes the gap where every surfaced "do you want me to apply this fix?" required a manual upload to be answerable from anywhere.
- **DDD surfaced decisions must include ace-web hosted artifact links** (0.2.134) — `agents/ddd.md` pause-policy section + every stop_* branch (`stop_concept_change`, `stop_unclear`, `stop_max_iter`) now require that surfaced `ReviewRequest` items include hosted ace-web screenshot URLs (NOT local `file://` paths), with an `element_locator` naming what the finding is about. Local paths fail the moment the user reads the message on another device; hosted URLs work everywhere. If upload fails, the agent says so explicitly and falls back to a verbal description, never a local path.
- **Auto-iterate gate based on per-finding `fix_kind`** (0.2.132) — judges
  now emit `fix_kind ∈ {mechanical, options, redesign}` per finding so the
  orchestrator can decide auto-apply vs ask WITHOUT re-parsing prose. The
  `/canopy:ddd-run` Step 5 report computes `auto_iterate_next_action ∈
  {continue, stop_done, stop_partial, stop_concept_change, stop_unclear,
  stop_max_iter}` and stamps it onto `run_state.yaml`. The `/canopy:ddd`
  agent's Converge-or-loop branches on it: mechanical findings auto-apply
  per route (PRODUCT → labs PR+merge+deploy, CONCEPT → spec edit,
  RESEARCH → why_brief edit, DEFER → log only), then re-fire the same
  scope. The loop stops only when `options`/`redesign` findings appear or
  max-iter is reached. Removes the previous behavior where ddd-run's
  "warn but no PRODUCT/CONCEPT-routed concrete fix" still stopped the
  agent and asked the user. Per the labs autonomy mandate, mechanical
  PRODUCT fixes auto-deploy from main without prompting.
- **Deck generator renders scene_total + partial-scope banner** (0.2.129) — `generate_presentation.py` now reads `scene_total` from the run-data sidecar and labels each scene slide "Scene N of M" (the original spec index/total), not "Slide 1/1". When the run-data carries `scenes_run` + `scene_filter` (from a `--scene` render), the title slide gets a "Partial run" banner naming the selector, the rendered scene indices, and that promotion requires a full-spec run. Backward-compatible: legacy run-data without those fields renders unchanged.
- **RunState gains `scenes_run` + `scene_filter` fields** (0.2.128) —
  makes the 0.2.127 SKILL.md contract real on the underlying pydantic
  model. Without it, `runstate.save()` rejected partial-run metadata.
- **`--scene <selector>` filter for walkthrough + ddd-run** (0.2.127) —
  run the canonical rubric on a subset of scenes when iteration only
  touched one scene's feature. Selector forms: `2` (index), `2,4,5`
  (list), `2-4` (range), `name-match` (title/spine substring).
  Preserves original scene indices in the output JSON and deck so a
  scene-2 score from a partial run is directly comparable to a scene-2
  score from a full run. Sidecar gains `scenes_run` + `scene_filter`
  fields. `run_state.yaml` carries the same. `/canopy:ddd-promote`
  hard-refuses partial runs at Step 0 — promotion requires full-spec
  coverage. Lets users stay on the DDD path instead of falling back to
  ad-hoc screenshots when iterating on a single scene's feature.
- **`patch-gstack-browse` skill** (0.2.124) — re-applies the SwiftShader WebGL
  patch to gstack `browse` so headless Chromium can render WebGL pages (Mapbox
  GL, three.js, deck.gl) for screenshot QA. Idempotent: patches
  `browser-manager.ts` with `--enable-unsafe-swiftshader`, rebuilds + re-signs
  the binary, restarts the daemon, and verifies a WebGL2 context. Re-run after a
  gstack update overwrites the source. Ships a `/canopy:patch-gstack-browse`
  command wrapper.
- **PAT-mint test harness** (0.2.121) — ported ace's PAT-mint test to canopy and
  added minimal vitest infrastructure to cover the canopy-web Personal Access
  Token loopback flow.
- **`canopy doctor` CLI** (0.2.120) — read-only plugin-health diagnostic (hook
  registration, session log, repo map, workbench token, plugin version) that exits
  non-zero so it can gate CI.
- **`canopy structure-drift` CLI** — one-pass self-audit of canopy's documented
  structural invariants: command/skill collisions following Pattern B,
  reserved-built-in-name collisions, version agreement across
  VERSION/plugin.json/marketplace.json, and the per-skill description budget.
  `--strict` makes it a CI gate.
- **`canopy:alignment` skill** (0.2.108) — a read-only two-project drift sweep that
  compares sibling systems and posts ranked, reasoned `[alignment]` findings to the
  canopy-web `/insights` feed. Added a matching canopy-web `[alignment]` category
  and divergence path.
- **`canopy:find-session` skill** — targeted lookup of your other active Claude Code
  session on a repo, for picking up context from a parallel worktree.
- **DDD (demo-driven-development) pipeline** — a large multi-PR arc building the
  demo-authoring loop: narrative-first spec authoring with first-class personas;
  a cohesive review surface; verifiable feature chunks with an actionability eval;
  build-order sequencing independent of video order; review edits (add/delete
  scenes, edit features, collect feedback); a narrative-coherence check that catches
  outcome leakage; and `ddd-promote`, which finishes the user-facing docs layer
  (capabilities, why-summary, poster, getting-started, play affordance).

### Changed
- DDD gates always use the canopy-web review surface; the narrative review now
  shows literal narrative sentences 1:1 with scenes.
- Default workflow is documented as always-PR with auto-merge (no maintainer
  review), and the plugin-update policy is documented as never hand-patching the
  installed plugin cache.

### Fixed
- `alignment` / `portfolio-review`: the canopy-web clear endpoint is `POST`, not
  `DELETE`.
- `ddd-promote`: fixed a urllib `UnboundLocalError` and tightened the `ddd-spec`
  persona rule (personas are people only).
- `ddd-actionability-eval`: sandbox the cold-derivation agents from the source repo
  so derivations stay independent.
