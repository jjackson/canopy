---
name: shareout
description: Generate a teammate-facing work briefing for a date range (default yesterday) — review your Claude Code sessions + your PRs per project, synthesize what shipped / why it matters / how teammates can leverage it, and post to the canopy-web /shareouts feed. Use when asked to "shareout", "what did I do yesterday", "briefing for the team", or "write up my week".
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available — run `/canopy:update`." Then continue.

# Shareout

Turn "what I worked on over a date range" into a **teammate-facing briefing**: one
section per project (what changed, *why* it matters, how to leverage it) plus a short
cross-project roll-up. Publishes to the **/shareouts** feed on canopy-web.

This skill is autonomous by default — gather, synthesize, post, hand back the URL.
Only stop to ask if the range is genuinely ambiguous.

## Inputs

- Default range: **yesterday** (single day). The user may pass a range in natural
  language — map it to `--from/--to` (YYYY-MM-DD) or `--days N`.
- `--days N` = the last N full days ending yesterday.
- `--project <name>` = limit to one repo (matches resolved repo ending `/<name>`).

## Flow

### 1. Gather the corpus (deterministic)

Run from the canopy repo. Write the corpus to a temp file so you can read it fully:

```bash
cd ~/emdash-projects/canopy
uv run canopy shareout gather --json-out /tmp/shareout-corpus.json
# add --days 7 / --from 2026-06-01 --to 2026-06-03 / --project canopy as needed
```

This collects, per project that had activity in the window:
- **sessions**: your Claude Code prompts (the intent → the *why*), tool-usage summary, MCP servers
- **prs**: your GitHub PRs (via `gh --author @me`) created/merged/updated in the window — title, state, body

Read `/tmp/shareout-corpus.json`. If `projects` is empty, tell the user there was no
tracked activity in the range and stop.

### 2. Synthesize the briefings (you, the agent)

For **each project** in the corpus, write a briefing for a teammate who wasn't in the
room. Ground every claim in the corpus (prompts + PR titles/bodies) — do not invent work.

Each project briefing:
- **title**: a plain, specific headline (what shipped). Not marketing.
- **summary**: one-sentence TL;DR for the feed card.
- **content**: markdown with these beats:
  - **What changed** — concrete, the shipped thing(s).
  - **Why** — the problem it solves / the decision behind it (mine the prompts for intent).
  - **How you can leverage it** — what a teammate can now do, reuse, or build on; gotchas.
- **links**: the *highlight* PRs (`{"label": "PR #83 — title", "url": "..."}`), 2–4 most
  relevant first. The full PR list is attached automatically in step 3 (don't hand-copy it).

Then write **one roll-up** across all projects: the 2–4 threads that tie the period
together, what's worth a teammate's attention first. Keep it short.

Write an authoring doc to a temp file in this shape:

```json
{
  "period_start": "2026-06-03",
  "period_end": "2026-06-03",
  "author": "<your name, e.g. jjackson>",
  "rollup": { "title": "...", "summary": "...", "content": "## ...", "links": [] },
  "projects": [
    { "project_slug": "canopy", "title": "...", "summary": "...", "content": "## What\n...\n\n## Why\n...\n\n## How you can leverage it\n...", "links": [{"label": "PR #83 — ...", "url": "..."}] }
  ]
}
```

- `period_start`/`period_end` come from the corpus `period`.
- `project_slug` must be a **canopy-web project slug**. Check available slugs:
  `curl -s -H "Authorization: Bearer $(cat ~/.claude/canopy/workbench-token)" "https://canopy-web-ujpz2cuyxq-uc.a.run.app/api/projects/slugs/" | python3 -c "import sys,json;[print(p['slug']) for p in json.load(sys.stdin)]"`
  Map each corpus repo (e.g. `jjackson/canopy`) to the matching slug (e.g. `canopy`).
  **Skip a project** (leave it out of the doc) if no slug matches — the server would
  skip it anyway.

### 3. Post

```bash
cd ~/emdash-projects/canopy
uv run canopy shareout post /tmp/shareout-authoring.json --corpus /tmp/shareout-corpus.json
```

`--corpus` auto-fills each project's full PR list (`all_prs`, rendered as a collapsed
"All N PRs" expander on the feed) by matching repo basename → project_slug — so you
only author the highlight `links`, not every PR. It stamps a unique `source` and posts.
Re-posting the same period **replaces** the prior rows for that period+source
(idempotent), so iterating is safe. Print the returned `View: …/shareouts` URL.

## Rules

- **Ground everything in the corpus.** Prompts reveal intent (the "why"); PR
  titles/bodies reveal what shipped. No invented features, no filler.
- **Teammate-facing, not a changelog.** Lead with why it matters and how to leverage it.
- **Honest.** If a day was small or exploratory, say so briefly — don't inflate.
- Slugs that don't exist on canopy-web are skipped; mention any skipped repos to the user.

## When NOT to use

- For the internal strategic brief over orchestrator state, use `canopy:brief`.
- For short categorized portfolio one-liners, use `canopy:portfolio-review` (/insights).
