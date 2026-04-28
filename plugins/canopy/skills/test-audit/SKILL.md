---
name: test-audit
description: Audit a Python/pytest project's test suite, score each test on 'is it pulling its weight,' and (by default) open a PR pruning the dumb ones. Use when asked to "audit tests", "prune dumb tests", "clean up the test suite", or "test-audit".
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# Test Audit

Audits a Python pytest suite and produces a per-test verdict (`keep`,
`refactor`, `prune`, `investigate`) grounded in superpowers TDD principles.
Default mode opens a PR with prunes/skip-marks; `--report-only` skips the PR.

## Default flow

1. Confirm the user is in a Python project with pytest tests. If not,
   stop and report.
2. Run from the project root:

   ```bash
   uv run --project ~/emdash-projects/canopy canopy test-audit .
   ```

3. Print the terminal summary. Mention the PR URL (or patch path) if one
   was produced.
4. Don't paraphrase the report. The PR body IS the report.

## Modes

- **Default (mode C):** runs full audit + opens a PR with prunes and
  env-fragile skip-marks. This is what the user runs day-to-day.
- **`--report-only` (mode A):** produces the audit but doesn't touch
  files. Use when the user wants to inspect first.
- **`--no-run`:** skips pytest; static analysis only. Faster, but misses
  flakiness and env-fragile tests.
- **`--reruns N`:** flake detection — re-runs the suite N extra times.
  Use when the user mentions flaky tests.
- **`--aggressive`:** applies prunes with score 4-6 in addition to 0-3.
  Only use when the user explicitly asks.

## Conservative apply rules

The applier only touches a test if:

| Verdict + reason | Action |
|------------------|--------|
| `prune`, env-fragile | `@pytest.mark.skip(reason="audit: ...")` |
| `prune`, score ≤ 3 | `git rm` the test |
| `prune`, score 4–6 | reported only (need `--aggressive`) |
| `refactor` / `investigate` | reported only, never applied |
| `keep` | no action |

## Output

- One-screen terminal summary (printed by the CLI).
- `.canopy/test-audits/<timestamp>/audit-report.md` — full human report.
- `.canopy/test-audits/<timestamp>/verdicts.yaml` — machine-readable.
- PR opened if `gh` is authenticated; otherwise a `.patch` file is written.

## Rules

- Python/pytest only in v1. If the project uses jest/vitest/go test, stop
  and report — don't try to adapt.
- Never push to main, never force-push. The applier always opens a PR on
  a fresh branch.
- If `gh` isn't authenticated, the applier writes a patch file and reports
  "would have opened PR with N changes" — don't crash.
- Don't dump the full report to the chat. The user has indicated they
  want terse, actionable output and the PR body is the audit.
