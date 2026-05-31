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
