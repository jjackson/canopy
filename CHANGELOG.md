# Changelog

All notable changes to canopy are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versions track the `VERSION` file and `plugins/canopy/.claude-plugin/plugin.json`,
which are kept in lockstep (every change under `plugins/canopy/` requires a patch
bump — see `.claude/CLAUDE.md`). The project does not tag releases. Pre-history
prior to the entries below was not formally changelogged; this file starts from the
recent, verifiable themes in the git log.

## [Unreleased]

### Added
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
