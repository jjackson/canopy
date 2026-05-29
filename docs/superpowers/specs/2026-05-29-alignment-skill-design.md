# `canopy:alignment` — cross-system drift sweep

**Date:** 2026-05-29
**Status:** Design approved, pending spec review

## Problem

The portfolio contains paired systems that evolve in parallel: the `ace` and
`canopy` Claude Code plugins, and the `ace-web` and `canopy-web` web apps. When
a capability, convention, or utility lands in one side, the sibling often lags —
either missing the feature entirely or solving the same problem a different way.
Even when both approaches work, the divergence is a tax: it costs context to
hold two mental models, and it hides opportunities to standardize.

There is no routine that asks, across two sibling systems: *what did one build
that the other should bring over or reconcile?*

## Goal

A read-only canopy skill, `canopy:alignment <projectA> <projectB>`, that compares
two passed-in projects across four axes, reasons case-by-case about which side
(if any) should be the reference, and surfaces ranked, actionable findings as
cards on the existing canopy-web `/insights` feed.

Report-only: it never writes to either repo and opens no PRs.

## Scope decisions (from brainstorming)

| Decision | Choice |
|---|---|
| How far it goes | **Report only** — no repo writes, no proposals store, no PRs |
| What's compared | The **two projects passed as arguments**; no whole-portfolio sweep, no stored config |
| Comparison axes | **All four**: features/capabilities, patterns/conventions, shared code/utilities, docs/UX surface |
| Recency | Used only to **rank** findings, not to choose what's scanned |
| Directionality | **Reasoned case-by-case** — each finding names a reference + lagging side with reasoning, or explicitly "no clear winner — reconcile". Not a fixed rule. |
| Output | **canopy-web `/insights` feed**, `source=canopy:alignment` |
| Architecture | Skill orchestrates; **one comparison subagent** does the heavy repo reading + reasoning (keeps the main context clean) |
| No args | **Ask the user** which two repos to align |

## Invocation

```
/canopy:alignment ace canopy
/canopy:alignment ace-web canopy-web
/canopy:alignment            # → asks which two repos to align
```

Each argument is a **slug**. The skill:
- resolves slug → local path by checking known bases in order:
  `~/emdash/repositories/<slug>`, then `~/emdash-projects/<slug>`
- uses the slug as-is when posting insight cards to canopy-web
- errors clearly if a slug resolves to no local repo

## Flow

1. **Preamble + sanity.** Run the canopy update check. Verify
   `~/.claude/canopy/workbench-token` is non-empty and canopy-web `/health/`
   returns 200 (override base URL with `CANOPY_WEB_API_URL`). Resolve both
   slugs → paths. Stop on any failure.
2. **Clear stale.** `DELETE /api/insights/clear/?source=canopy:alignment`, with
   the same OAuth/401 fallback portfolio-review documents (dismiss one-by-one,
   or skip and let cards pile up).
3. **Dispatch one comparison subagent.** Inputs: both repos' local paths, the
   four axes as a checklist, and the case-by-case directionality instruction.
   The agent reads both repos, identifies divergences, and returns structured
   findings (schema below). A single subagent keeps heavy repo reading out of
   the main session context.
4. **Rank.** Order findings by recency (last-touched date of the affected area,
   via git) and impact. Recent work floats to the top.
5. **POST.** Each finding becomes a one-sentence card POSTed to the **lagging**
   side's slug at `/api/projects/<slug>/context/` with
   `context_type=insight`, `source=canopy:alignment`. Category is `[opportunity]`
   (borrow/share) or `[pattern]` (divergent approach) — both already render on
   the feed, so **no canopy-web change is required**. Stop on the first 401.
6. **Summary.** Print counts (findings posted, failures with HTTP codes) and
   `View at: <CANOPY_WEB>/insights`.

## Finding schema (subagent return)

One row per finding:

```
axis:        features | patterns | shared-code | docs-ux
reference:   <slug>  | "none — reconcile"
lagging:     <slug>
reasoning:   why this side is the reference, or why there's no clear winner
evidence:    file / commit / path on BOTH sides
recency:     last-touched date of the area (for ranking)
card:        one sentence ending in an action verb (the text actually posted)
```

## Card discipline (reused from portfolio-review)

- **One claim per card.** Multiple claims → multiple cards.
- **Cite the handle on both sides.** File path, commit SHA, command name, etc.
- **Action verb at the end.** "adopt", "reconcile", "extract", "consider".
- **One sentence.** Hard cap.
- **Empty is allowed.** If the two systems are well-aligned on an axis, emit
  nothing for it. Don't pad.

Example cards:
- `[opportunity] ace ships PAT-mint loopback auth (commands/*-pat-mint.md); canopy-web uses an older shared-secret flow — adopt the loopback shape.`
- `[pattern] ace and canopy resolve plugin install paths differently (ace: lib/, canopy: inline python one-liner) — standardize on canopy's installed_plugins.json reader.`

## Files

- `plugins/canopy/skills/alignment/SKILL.md` — the orchestration procedure above
- `plugins/canopy/commands/alignment.md` — **Pattern B**: reads the SKILL.md from
  the resolved plugin install path and follows it, to avoid the command/skill
  name-collision foot-gun documented in CLAUDE.md
- VERSION + `plugins/canopy/.claude-plugin/plugin.json` bumped via
  `canopy version bump`; ship, then `/canopy:update`

## Non-goals (YAGNI)

- No config file and no bootstrap (projects are passed as args).
- No repo writes, no PRs, no canopy proposals/observations entries.
- No new canopy-web insight category, endpoint, or frontend change.
- No persistent findings DB — the insights feed is the store, cleared per
  `source` each run.
- No auto-discovery of sibling pairs.
- No N-way / >2 project comparison (exactly two projects per run).

## Open risks

- **Slug ≠ canopy-web project.** If a passed slug isn't a curated project on
  canopy-web, the POST will fail. The skill should surface this clearly rather
  than silently dropping the card (report the HTTP code in the summary).
- **Large-repo context.** Even two repos across four axes is substantial; the
  comparison subagent must read selectively (entry points, command/skill
  manifests, lib/ utilities, CLAUDE.md, recent diffs) rather than exhaustively.
