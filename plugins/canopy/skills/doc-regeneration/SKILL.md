---
name: doc-regeneration
description: Audit project documentation for staleness and coverage gaps, then regenerate CLAUDE.md and learnings. Use when docs may be out of sync with actual project state.
version: 0.2.0
---

# Doc Regeneration v2

## Purpose

Audit CLAUDE.md and docs/ against the actual project state (GitHub issues, PRs, learnings), then produce a corrected version. The goal is ensuring an AI agent starting a new session has accurate, complete context — no stale status, no missing learnings, no confusing contradictions, and no wasted context window on historical detail.

## Modes

**Dry-run (default):** Generate all output into `docs/.dry-run/`. Nothing is committed or branched. Review the output and decide what to apply.

**Apply:** Create a `docs/regen-YYYY-MM-DD` branch, write the regenerated files, and create a PR.

To select mode, the invoker specifies `--dry-run` or `--apply` when calling the skill. Default is `--dry-run`.

## Process

### Phase 1: Read Everything (no output yet)

Read these inputs. Do NOT produce any output until all inputs are gathered:

1. **CLAUDE.md** — read the full file
2. **docs/learnings/** — read every file, note each learning's key takeaway
3. **docs/plans/** — read headers and status sections only (skip large plan bodies — just read the first 50 lines for context)
4. **GitHub issues** — run `gh issue list --state all --limit 100` to get current state. If 100 results returned, paginate with `--limit 200`. Warn in the report if results were truncated.
5. **GitHub PRs** — run `gh pr list --state all --limit 100` to get merged/open PRs. Paginate if needed. Warn if truncated.

### Phase 2: Analyze (four checks)

**Check 1 — Staleness:**
Compare CLAUDE.md's status table against GitHub issue states. For each wave/task:
- Is the status in CLAUDE.md correct? (Open vs Done, issue number, file count)
- Does the PR link match?
- Are any completed items still marked as Open/Blocked?
- Do file counts in the Project Structure section match actual counts on disk?

**Check 2 — Coverage:**
For each learning in `docs/learnings/`:
- Is the learning's key takeaway reflected somewhere in CLAUDE.md? (Checklist item, guideline, key doc reference, etc.)
- If not, what section of CLAUDE.md should it be added to?

Also check:
- Are there patterns from merged PRs or closed issues that should be learnings but aren't?
- Are any docs/plans referenced in CLAUDE.md that don't exist or are obsolete?
- Do any learning files contradict each other? Flag contradictions explicitly.

**Check 3 — Checklist Drift:**
If CLAUDE.md contains a checklist or rules section:
- Are any checklist items never referenced in any learning file? (potentially dead rules — flag them)
- Do any learnings suggest patterns that should be checklist items but aren't? (missing rules)
- Are any checklist items redundant or overlapping?
- Note: flag but don't remove potentially dead rules — they may still apply to downstream consumers.

**Check 4 — Size & Structure:**
- Count total lines in CLAUDE.md
- Break down by section (header, status, key docs, checklists, rules, etc.)
- Identify sections that could be compressed:
  - Completed phase/milestone tables → collapse to one-liner summaries with links to completion reports
  - Historical plan references → keep completion reports, drop individual phase plans
  - Flat learning lists → categorize by topic
- Target: keep CLAUDE.md under ~200 lines of essential content. Every line must earn its place in the agent context window.

### Phase 3: Produce Output

Generate these files:

**`review-report.md`** — The core deliverable. Contains:
1. **Staleness findings** — table of what's wrong, with corrections
2. **Coverage findings** — table of each learning and whether it's reflected in CLAUDE.md
3. **Checklist drift findings** — dead rules, missing rules, redundancies
4. **Size analysis** — current line count, breakdown by section, compression recommendations
5. **Opinionated assessment** — "If I were an agent starting today, here's what would confuse me and what I'd need." Be specific and direct.
6. **Recommended changes** — bullet list of what the regenerated CLAUDE.md changes

**`CLAUDE.md`** — The regenerated version. Rules:
- Preserve the existing structure and section order exactly
- Update status information to match GitHub reality
- Compress completed milestones: replace detailed tables with one-liner summaries linking to completion reports. Only keep detailed tables for the CURRENT active phase (if any).
- Add missing learning/plan references — categorize learnings by topic rather than listing chronologically
- Do NOT add new sections unless a learning explicitly calls for one
- Do NOT remove or rewrite content that is already correct
- Mark completed/obsolete plans appropriately in Key Docs

**`changes.diff`** — A human-readable narrative diff (NOT a git diff). Organized by section, showing what changed and why. Include a summary table at the end with counts of: factual corrections, compressions, additions, structural changes, lines saved.

**`learnings/<name>.md`** (only if gaps found) — New learning docs for patterns discovered in PRs/issues that aren't captured yet. Use the existing learning format:
```
# Learning: <Title>

**Date**: YYYY-MM-DD
**Context**: <where this came from>
**Status**: <Resolved/Active>

## Problem
<what went wrong or was discovered>

## Root Cause
<why>

## Fix / Key Takeaway
<what to do differently>
```

### Phase 4: Deliver

**If dry-run (default):**
1. Create `docs/.dry-run/` directory
2. Write `docs/.dry-run/review-report.md`
3. Write `docs/.dry-run/CLAUDE.md`
4. Write `docs/.dry-run/changes.diff`
5. Write any new learnings to `docs/.dry-run/learnings/`
6. Present the review report to the user
7. Suggest: "Review `docs/.dry-run/` and compare against current docs. When ready, re-run with `--apply` to create a PR."

**If apply:**
1. Create branch `docs/regen-YYYY-MM-DD`
2. Write regenerated CLAUDE.md to repo root
3. Write any new learnings to `docs/learnings/`
4. Commit with message `docs: regenerate documentation (staleness + coverage fixes)`
5. Create PR targeting `main`

## Key Principles

- **Read before write.** Gather ALL inputs before producing ANY output.
- **Preserve structure.** CLAUDE.md's section order is intentional. Don't reorganize.
- **Be opinionated.** The assessment should say what would confuse a new agent, not just list facts.
- **Minimal changes.** Only change what's wrong or missing. Don't rewrite correct content.
- **Evidence-based.** Every finding must cite the source (issue number, learning filename, PR number).
- **Size-conscious.** CLAUDE.md is loaded into every agent context. Every line must earn its place. Completed milestones become one-liners; active work gets detail.
