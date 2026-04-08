---
name: doc-regeneration
description: Audit project documentation for staleness and coverage gaps, then regenerate CLAUDE.md and learnings. Use when docs may be out of sync with actual project state.
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
[ -n "$_CANOPY_UPD" ] && echo "$_CANOPY_UPD"
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# Doc Regeneration v2

## Purpose

Audit CLAUDE.md and docs/ against the actual project state (GitHub issues, PRs, learnings), then produce a corrected version. The goal is ensuring an AI agent starting a new session has accurate, complete context — no stale status, no missing learnings, no confusing contradictions, and no wasted context window on historical detail.

## Modes

**Dry-run (default):** Generate all output into `docs/.dry-run/`. Nothing is committed or branched. Review the output and decide what to apply.

**Apply:** Create a `docs/regen-YYYY-MM-DD` branch, write the regenerated files, and create a PR.

To select mode, the invoker specifies `--dry-run` or `--apply` when calling the skill. Default is `--dry-run`.

## Genesis mode (no existing CLAUDE.md)

If the project has no CLAUDE.md at repo root, the skill runs in **genesis mode**:

- Checks 1 (Staleness), 3 (Checklist Drift), and 4 (Size) in Phase 2 degenerate to "n/a" — there's no prior doc to compare against. Note this explicitly in the review report; do not silently skip.
- **Check 5 (Reference Integrity) becomes mandatory, not optional.** When authoring a CLAUDE.md from scratch, the skill is transcribing facts from README, plans, and code into the highest-visibility doc in the repo. Every path, file count, table row, and external reference must be traced to a file read or shell command run in this session. No transcription from README or plan files without an independent `test -e` / `ls` / `wc -l` on the claim.
- Prefer fewer verified facts over more unverified ones. If a reference can't be verified, omit it or mark it `TODO: verify <reason>` in the draft so the user catches it in review.

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

**Check 5 — Reference Integrity:**
For every file path, directory, cross-repo reference, and link that appears in the current CLAUDE.md OR would be copied from README/plans/learnings into the regenerated CLAUDE.md:

- Run `test -e <path>` (absolute or resolved relative to repo root) before trusting the reference.
- For cross-repo references (e.g. `../ace/docs/...`), resolve and `ls` the target. Do not trust sibling-repo paths just because README mentions them.
- If a reference is broken:
  1. **Do not copy it verbatim into the regenerated CLAUDE.md.** Elevating a broken reference into the highest-visibility doc makes staleness worse.
  2. Try to find the real file: glob the parent directory for the nearest match by name or date stamp.
  3. Record the finding in the review report under **Staleness → broken references**, including: where the bad path came from (README, plan file, old CLAUDE.md), the path that was claimed, and the path that actually exists (if found).
  4. If the broken reference lives in a source-of-truth doc (README, plan), flag it as a follow-up fix to that doc — don't silently "fix it forward" by only correcting CLAUDE.md.
- File-count claims in CLAUDE.md (e.g. "10 Python files, 5 tests") must be re-counted at regen time, not copied from an older CLAUDE.md or plan. Either re-count, or omit — never transcribe stale counts.

**Principle:** the skill's own output becomes a source of truth for the next agent. A broken path written to CLAUDE.md is worse than the same broken path in README, because CLAUDE.md is loaded into every session's context.

### Phase 3: Produce Output

Generate these files:

**`review-report.md`** — The core deliverable. Contains:
1. **Staleness findings** — table of what's wrong, with corrections
2. **Coverage findings** — table of each learning and whether it's reflected in CLAUDE.md
3. **Checklist drift findings** — dead rules, missing rules, redundancies
4. **Size analysis** — current line count, breakdown by section, compression recommendations
5. **Reference integrity findings** — broken paths, bad cross-repo refs, and which source doc propagated them. Include "verified: N references checked, M broken" even when M=0.
6. **Opinionated assessment** — "If I were an agent starting today, here's what would confuse me and what I'd need." Be specific and direct.
7. **Recommended changes** — bullet list of what the regenerated CLAUDE.md changes

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
- **Evidence-based.** Every finding must cite the source (issue number, learning filename, PR number). Every path or file reference written into the regenerated CLAUDE.md must be verified to exist on disk this session — citing README as the source is not enough if README is itself stale.
- **Size-conscious.** CLAUDE.md is loaded into every agent context. Every line must earn its place. Completed milestones become one-liners; active work gets detail.
