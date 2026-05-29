# Canopy — agent & contributor guide

Canopy is a Claude Code **plugin**: self-improving workflow skills (session analysis,
improvement cycles, PM supervision, the DDD demo-driven-development loop, walkthrough
eval, and learning loops). This repo (`plugins/canopy/`) is the **source of truth**.

## Golden rule: never patch the installed plugin directly — always go through the plugin

There are three copies of canopy on a machine. Only the first is editable:

| Location | What it is | May I edit it? |
|----------|------------|----------------|
| `plugins/canopy/` in **this repo** | Source of truth | ✅ **Yes — all changes start here** |
| `~/.claude/plugins/cache/canopy/canopy/<version>/` | The **installed** plugin Claude Code actually runs | ❌ **Never hand-edit** |
| `~/.claude/plugins/marketplaces/canopy/` | The update **channel** `/canopy:update` pulls from | ❌ Never edit/develop here |

**Do not hand-edit the installed cache or the marketplace checkout to "make a fix take
effect now."** That fix is invisible, unversioned, and gets silently overwritten on the
next update — and it diverges every machine. If you catch yourself editing a path under
`~/.claude/plugins/`, stop: that is the symptom of skipping the release flow.

## The only supported way to change canopy

1. **Edit the source** under `plugins/canopy/` in this repo.
2. **Bump the version** in **both** `VERSION` and
   `plugins/canopy/.claude-plugin/plugin.json` (and the `version` fields in
   `.claude-plugin/marketplace.json`). The `version-check` CI fails if `VERSION` and
   `plugin.json` disagree, and requires the version to advance past `origin/main` on
   any plugin change.
3. **Open a PR to `main`.** The default workflow is **always-PR + auto-merge** (no
   maintainer review required) — never commit straight to `main`, and never push a
   diverged local `main`.
4. After it merges, **install it the proper way: `/canopy:update`** (which pulls the
   marketplace checkout from GitHub `main` and installs the new version into the cache),
   then `/reload-plugins`.

Releases are **version-on-`main`** — there are no git tags. "Released" means merged to
`main` with the version bumped; `/canopy:update` distributes it.

## Repo notes

- `scripts/ddd/` (DDD loop helpers) ships in **this repo**, not the plugin cache. Skills
  resolve it via `DDD_REPO=$HOME/emdash-projects/canopy` (fallback
  `~/.claude/plugins/marketplaces/canopy`) and run `uv run python -m scripts.ddd.<mod>`.
- DDD pause gates (`concept_change`, `external_release`, the narrative-agreement gate)
  post to the **canopy-web review surface**, never the built-in `AskUserQuestion` tool.
  See `plugins/canopy/agents/ddd.md` § Pause policy.
