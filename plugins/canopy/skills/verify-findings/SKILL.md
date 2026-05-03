---
name: verify-findings
description: Re-verify session-review findings against the current state of their target repos. Catches findings whose fix already shipped between when the review was generated and when the user is about to act on them. ALWAYS invoke at the end of session-review (before presenting the table) and before any implementation work on findings.
---

# Verify Findings

Re-check session-review findings against the current state of their
target repos. Drops or annotates any whose fix already shipped, so the
user doesn't waste time implementing work that's already done.

## Why this skill exists

The session-review pipeline observes friction in past Claude Code
sessions and emits proposals. Between proposal-time and act-time,
the target repo's main branch keeps moving — often the very fix the
proposal recommends has already shipped. This was the dominant
failure mode of the May 1 ace review: 11 of 17 findings were already
in `main` at versions `0.10.56`–`0.10.69` before the user saw the
table. Implementing them again would have been wasted work.

This skill formalizes the verification pass so it always runs and is
testable, instead of being an inlined sub-step of the session-review
agent that the agent sometimes skipped.

## When to invoke

- **End of session-review (REQUIRED).** Before the agent presents the
  ranked findings table to the user, run this skill against every
  proposal it would otherwise show. Drop `shipped` proposals; annotate
  `partial` ones with the evidence; let `open` ones pass through.
- **Before acting on findings (REQUIRED).** When the user signals
  "do these" — `auto-improve`, "implement #5", "do all of them" —
  re-verify the targeted findings first. The user may have come back
  hours/days after the review; the world has moved.
- **On demand.** `/canopy:verify-findings <id-prefix>...` lets the
  user re-check specific proposals without running a full review.

## Inputs

Either:

- A space-separated list of proposal-id prefixes (8+ chars per
  prefix; matches `~/.claude/canopy/proposals/<prefix>*.yaml`).
- The literal `--all-pending` to verify every proposal whose status
  is currently `pending`.

If no input is provided, default to `--all-pending`.

## Process

### Step 1: Load proposals

```bash
# Specific IDs
for prefix in $ARGS; do
  ls ~/.claude/canopy/proposals/${prefix}*.yaml 2>/dev/null
done

# Or all-pending
grep -l 'status: pending' ~/.claude/canopy/proposals/*.yaml 2>/dev/null
```

For each YAML, parse:

- `id` — full proposal hash
- `action` — what the proposal would change (this is the primary
  search corpus for verdicts)
- `target_repo` — the proposal's repo target. **Resolve to a local path
  via** `orchestrator.repo_paths.resolve_repo_path(target_repo)` — that
  function accepts both a short name (`"ace"`) and an existing-path style
  (`"~/emdash-projects/ace"`) and searches every known emdash root. Don't
  hardcode either path convention; different logins on the same machine
  put repos under different roots
- `observation_id` — links back to the source observation
- `created` — when the proposal was generated (use this as the
  earliest commit window)
- `status` — skip proposals already marked `obsolete` or
  `implemented`; verify `pending` and `failed` (failed retry might
  have been fixed by a different code path)

If `resolve_repo_path(target_repo)` returns `None` (no checkout under
any known emdash root on this machine), mark the proposal
`unverifiable: target repo not on this machine` and move on. Do **not**
try to clone repos. Concrete pattern:

```bash
# Inside the loop over proposals:
LOCAL=$(uv run python3 -c "from orchestrator.repo_paths import resolve_repo_path; p=resolve_repo_path('$TARGET'); print(p) if p else exit(2)" 2>/dev/null)
if [ -z "$LOCAL" ]; then
  echo "unverifiable: $TARGET not on this machine"
  continue
fi
cd "$LOCAL" && git fetch origin main 2>/dev/null
```

### Step 2: Pull the latest origin/main of each target repo

For each unique target_repo across the proposal set:

```bash
cd "<target_repo>" && git fetch origin main 2>/dev/null
git rev-parse origin/main
```

Capture the latest sha. If the repo is dirty or on a non-main branch,
prefer `origin/main` over local `HEAD` to avoid grading against
in-flight work.

### Step 3: Build the evidence corpus per repo

For each target_repo, gather the commits + changelog tail since the
earliest proposal-creation date in scope:

```bash
cd "<target_repo>"
EARLIEST="<min(proposal.created) - 2 days>"   # 2-day buffer
git log origin/main --since="$EARLIEST" \
  --pretty=format:'%h %ad %s' --date=short | head -80
[ -f CHANGELOG.md ] && head -200 CHANGELOG.md
```

Hold this in your context — it's the single evidence corpus you
match every per-repo proposal against. Don't re-fetch per proposal.

### Step 4: Per-proposal verdict

For each proposal:

1. **Search the evidence corpus** for keywords from the proposal's
   `action` field. Mine the action for the changed verbs and named
   nouns — e.g. for action `"Wrap add_fields in retry-with-get_form
   verification"`, search for `add_fields`, `retry`, `get_form`,
   `verify`. Spot any commit subject or changelog bullet that
   describes the same fix.

2. **Grep for code-level claims.** If the action mentions a specific
   function name, file path, regex, or symbol, grep the repo to
   confirm the fix is present in current code:

   ```bash
   cd "<target_repo>" && grep -rn "<symbol-or-string>" \
     --include="*.ts" --include="*.py" --include="*.sh" \
     --include="*.md" .
   ```

3. **Pick a verdict from this table:**

   | Verdict        | Criteria                                                                                       |
   |----------------|------------------------------------------------------------------------------------------------|
   | `shipped`      | A commit + changelog entry both describe the proposed fix end-to-end, AND the code currently reflects it (grep confirms). |
   | `partial`      | Some of the fix shipped: a different solution was chosen for the same root issue, OR one of N affected files was updated. |
   | `open`         | No commit or changelog hits, AND grep confirms the original symptom is still present.          |
   | `unverifiable` | Target repo not on this machine, OR the action is too vague to grep, OR the proposal predates target_repo's earliest commit. |

4. **Cite evidence.** Every non-`open` verdict must name the
   commit sha + version (if a CHANGELOG section is bumped) + a
   one-line excerpt of the changelog or grep result. Verdicts
   without specific evidence are inadmissible — fall back to
   `unverifiable` if you can't cite.

### Step 5: Update proposal state

For each `shipped` verdict, append to the proposal YAML:

```yaml
status: obsolete
verified:
  date: <YYYY-MM-DD>
  by: verify-findings
  shipped_at: <commit-sha>
  shipped_in_version: <version-from-changelog-if-any>
  evidence: <one-line excerpt>
```

For each `partial` verdict, **do not change `status`** but append
the same `verified:` block — the user may still want to act on the
remaining gap.

For `open` and `unverifiable`, do not modify the proposal YAML.

Use `python3` + a small inline script to do the YAML edit safely
(don't sed-edit YAML — append the block at the end of the file
preserving existing fields).

### Step 6: Emit triage

Print a table:

```
| status         | id           | finding (action excerpt)              | evidence                              |
|----------------|--------------|---------------------------------------|---------------------------------------|
| shipped        | 85cbef676ae2 | Nova add_fields retry-with-verify     | 0.10.77 (d968d2e); CHANGELOG hits     |
| partial        | fbeac13427d4 | Connect REST API probe                | 0.10.64 chose HTMX fallback instead   |
| open           | a7f633e915cb | macOS launchd OP_SERVICE_ACCOUNT      | no commit since 2026-05-01; grep ✓    |
| unverifiable   | <hash>       | <action>                              | scout repo not on this machine        |
```

Plus a one-line summary at the bottom:

```
verify-findings: 11 shipped · 1 partial · 5 open · 0 unverifiable
```

### Step 7: Hand off

The skill caller decides what to do next, but the skill contract is:

- **If invoked from session-review's Step 5:** drop `shipped`
  proposals from the findings table the agent presents, annotate
  `partial` rows with the evidence, let `open` rows pass through.
- **If invoked from a user "implement these" flow:** before
  dispatching any implementation, ask the user explicitly: "Skip
  the <S> shipped proposals?" with the list. Default to skip on
  enter. Implement only the user's confirmed set.
- **If invoked standalone (`/canopy:verify-findings`):** print the
  triage table and stop. The user reads it.

## Honest limits

- **Equivalent fixes via different solutions register as `partial`,
  not `shipped`.** Example: proposal asks for "structured error
  message naming each inaccessible doc"; team shipped "fall back to
  HTML wizard parsing." Same root issue, different solution. The
  evidence shows it but the verdict can't claim full coverage. Read
  partial-evidence carefully before re-implementing.
- **Vague actions are unverifiable.** If the action is "improve
  error reporting" with no specific symbol or file, there's nothing
  to grep. Use `unverifiable`. Don't pretend to grade.
- **Sub-day commits can race the review.** A fix that lands in the
  same hour as the session-review may not be in the proposal's
  context yet. The verdict will say `shipped` even though the
  proposal was generated correctly at the time. That's the right
  outcome — drop the obsolete finding.
- **Worktrees are honored.** `resolve_repo_path` returns the main
  checkout (under whichever emdash root convention this machine uses
  — `~/emdash/repositories/<repo>`, `~/emdash-projects/<repo>`,
  etc.); it does NOT search worktrees, which are per-task and not the
  source of truth for verification. If the main checkout is missing
  on this machine the proposal is unverifiable here, even if a
  worktree happens to exist.
