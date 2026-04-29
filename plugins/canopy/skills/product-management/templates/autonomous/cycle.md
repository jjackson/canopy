# Autonomous PM cycle (Phases A–E)

This is the procedure executed by `/canopy:pm-autonomous` for one sprint. Read it top-to-bottom before starting; do NOT improvise the order.

The sprint succeeds when a customer-quality release-notes email is sent. It fails (gracefully) when convergence isn't possible — in which case a minimal "stuck" email is sent and the sprint stops.

This skill is project-agnostic. ALL project-specific knobs live in `~/.canopy/pm/<project>/autonomous.yaml` — see `config-schema.md`.

## Phase 0 — Pre-flight

Run sequentially, NOT in parallel (`$CANOPY_PM_DIR` may not exist yet on a fresh project):

1. Resolve `$PLUGIN_PATH` and `$CANOPY_PM_DIR` once and reuse:

   ```bash
   PLUGIN_PATH=$(python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'])")
   CANOPY_PM_DIR="$HOME/.canopy/pm/$(basename "$(git rev-parse --show-toplevel)")"
   mkdir -p "$CANOPY_PM_DIR"
   ```

2. **If `$CANOPY_PM_DIR/autonomous.yaml` is MISSING, bootstrap it before validating — do NOT ask the user.** This skill defaults to autonomous; the user has already opted in by running this command. Derive defaults from project signals and write the file directly:

   - `email.to` = `git config user.email`
   - `email.from` = same as `email.to` for v1 (the user can swap to a service mailbox later)
   - `email.subject_prefix` = `[<basename of repo>]` (from `git rev-parse --show-toplevel`)
   - `email.sender_skill` = if `~/.claude/plugins/installed_plugins.json` lists `ace@ace`, use `ace:email-communicator`; otherwise leave the literal string `ace:email-communicator` and proceed (the user can swap it in `$CANOPY_PM_DIR/autonomous.yaml` if a different sender ships first)
   - `shipping.branch_prefix` = `<basename of repo>/auto/`
   - `shipping.pr_label` = `autonomous`
   - `shipping.merge` = `squash`
   - `shipping.deploy_command` and `shipping.deploy_workflow` — look in `.github/workflows/` for the most recently-modified `deploy*.yml` and use it. If none exists, write `echo "no deploy configured"` / `none.yml` and continue (the gate will catch deploy failures later if they matter)
   - `shipping.post_deploy_health` — look for any URL in README.md / CLAUDE.md matching `https?://[^ ]+/(health|api/health|healthz)`. If none, fall back to `["https://example.invalid/health"]` and continue (a 5xx is fine, the cycle will fix-forward)
   - `testing.unit` / `lint` / `types` — guess by detecting `pyproject.toml` (→ `uv run pytest -q` / `uv run ruff check .` / `uv run mypy .`), `package.json` (→ `npm test` / `npm run lint` / `npm run typecheck`), or fall back to `true` (no-op) for any not detectable
   - `testing.dogfood.start_command` — if `docker-compose.yml` or `compose.yaml` exists, use `docker compose up -d`; otherwise `true`. `wait_for` and `base_url` default to `http://localhost:8000/health` and `http://localhost:8000`. `headless_browser_skill` = `gstack`
   - `guardrails`: `one_pr_in_flight: true`, `diff_size_limit_lines: 1500`, `max_fix_forward_attempts: 3`
   - `theme_detection.lens_rotation`: `[user-value, adoption-blockers, integration-depth, trust-reliability, tech-debt]`

   Write the YAML to `$CANOPY_PM_DIR/autonomous.yaml`, print a single line: `Bootstrapped $CANOPY_PM_DIR/autonomous.yaml from project defaults (deploy=<workflow-or-none>, sender=<sender>, lens_rotation=5).` Then continue. Do NOT ask the user to confirm — they can edit the file later if anything's wrong.

3. Validate `$CANOPY_PM_DIR/autonomous.yaml`. The validator declares its YAML dep via PEP 723 inline metadata, so invoke it with `uv run --script` (NOT plain `python3`) — that way uv resolves PyYAML on the fly without requiring it on the user's system python:

   ```bash
   uv run --script "$PLUGIN_PATH/skills/product-management/scripts/validate_autonomous_config.py" "$CANOPY_PM_DIR/autonomous.yaml"
   ```

   Refuse to run on non-zero exit. Print the validator stderr and stop. If `uv` is missing on the user's system, ask them to install it (`brew install uv` or `pip install uv`) and stop. Note: if the file existed already (i.e. the user supplied it), still validate — never silently overwrite a user-supplied config.

4. Read `$CANOPY_PM_DIR/context.md` and `$CANOPY_PM_DIR/learnings.md`. If `context.md` is missing, run the existing skill's bootstrap flow first (see SKILL.md "Bootstrapping: Building context.md"), THEN re-enter Phase 0.

5. Capture the **starting branch** (so Phase E can return to it) and confirm `origin/main` is reachable:

   ```bash
   STARTING_BRANCH=$(git rev-parse --abbrev-ref HEAD)
   git fetch origin main
   ```

   The skill is **worktree-friendly**: it does NOT require you to be on `main` and does NOT require a clean working tree. Phase C creates its branches from `origin/main` directly (not from your current HEAD), so unrelated WIP in your worktree is preserved and never contaminates the autonomous PR. If `git fetch` fails, stop and report — without `origin/main` we can't branch safely.

6. Confirm only ONE autonomous PR is in flight (per `guardrails.one_pr_in_flight`). Query:

   ```bash
   gh pr list --label "$PR_LABEL" --state open --json number,headRefName
   ```

   If a previous autonomous PR is still open, RESUME that PR instead of starting fresh — pick up at Phase C and drive it to merge before opening anything new.

## Phase A — Working-backwards draft (5–10 min)

Goal: produce a target email DRAFT that can pass three critiques before any engineering happens.

1. Quick scout pass across the lenses in `theme_detection.lens_rotation`. Just enough breadth to see what's ripe — no deep dives.
2. Draft the target email using `email-format.md`'s template, AS IF IT WERE ALREADY TRUE. Specific feature names. Specific value statements. No placeholders.
3. Self-critique against three tests; write the verdict for each into the cycle log:
   - **Clear:** Could a non-technical user read this and know what's better today than yesterday? Does each highlight name a concrete thing they can click on?
   - **Testable:** For each highlight, can I write a one-line "Try it" instruction that proves it works? If a highlight doesn't survive a "go click this URL and see X happen" test, it's vapor — drop it.
   - **Impressive:** Does this move the product forward in a way the user would *care about*? Not "code is cleaner" — "you can now do thing-Y you couldn't before, or thing-Z is meaningfully nicer." If the most exciting highlight is "polished some copy," the answer is no.
4. If any critique fails, LOOP on Phase A. Scout deeper. Swap a weak highlight. Change the theme. Expand scope. Do NOT proceed to Phase B with a draft that is not yet impressive — that is the single most important rule of this skill.

The approved draft, with every critique annotated PASS, is the input to Phase B.

## Phase B — Derive the work

For each highlight in the approved draft, write one or more concrete proposals — title, files, expected diff shape, validation. Estimate effort per proposal. If the total estimated effort exceeds ~6 hours of cycle time, TRIM: keep the most "Try it"-able subset and save the rest as a future-sprint note in the run log.

## Phase C — Ship

For each proposal, in order, ONE PR IN FLIGHT AT A TIME:

1. Create branch FROM `origin/main` (not from current HEAD — the user is often in a worktree on an unrelated feature branch). `git fetch` already ran in Phase 0; assume `origin/main` is fresh:

   ```bash
   git checkout -b "$BRANCH_PREFIX$(slug-of title)" origin/main
   ```

   This guarantees the autonomous PR's diff contains ONLY the work this proposal does, regardless of the worktree's pre-existing state.
2. Implement the change. Use TDD where it fits (`superpowers:test-driven-development`); skip TDD only when the change is purely a behavior-of-no-test-yet thing and a test would be theatre.
3. Stage the change: `git add -A`
4. Run the full convince-self-it's-clean gate per `convince-self-gate.md` — sections 3a then 3b then 3c (if this proposal corresponds to a "Try it" highlight).
5. If the gate drops the proposal, log it under `self-review-blocked` in the run log AND re-derive the corresponding email highlight (try a different angle, or drop it and scout for a replacement). The email must remain impressive or it's not worth sending.
6. Open PR: `gh pr create --label "$PR_LABEL" --base main --title "<title>" --body "<body>"`. Body cites the email highlight this proposal makes true.
7. Wait for CI. On red:
   - Up to 2 fix-forward attempts on the same PR (re-run the gate each time)
   - Beyond that, switch this PR to a fix-forward investigation cycle. Track attempts against `guardrails.max_fix_forward_attempts`.
   - If exhausted, log "stuck", call Phase E with a stuck-state email, exit.
8. On CI green: merge per `shipping.merge`.
9. Run `shipping.deploy_command`.
10. Poll deploy status (use `gh run list --workflow="$DEPLOY_WORKFLOW"` until completion).
11. Run section 3d post-deploy health check.
12. Update the cycle log with: branch, PR number, gate verdicts (each Q answered), deploy status, health-check status.
13. Move to the next proposal.

## Phase D — Reality reconciliation

Reality always diverges from plan. Before sending the email:

1. Rewrite the email body based on what ACTUALLY shipped — which highlights survived, what new value emerged, what got cut.
2. Re-run the three critiques (Clear, Testable, Impressive) on the rewritten version.
3. **Also ask:** "What did I learn about the PM process itself this sprint?" Universal lessons (NOT project-specific) become a separate canopy PR per `SKILL.md`'s Self-Improvement Protocol. Link them in the email's `**` section.
4. If the rewritten email still passes → proceed to Phase E.
5. If it doesn't → do NOT send a weak email. Log "sprint failed to converge on a great email" in the run log, build the stuck-state email body per `email-format.md`, proceed to Phase E.

## Phase E — Send + stop

1. Render the email body to `$CANOPY_PM_DIR/sent-emails/<YYYY-MM-DD-theme-slug>/email.md`. Copy the dogfood screenshots into the same directory's `screenshots/` subfolder.
2. Invoke `email.sender_skill` with `subject`, `body_markdown`, `attachments`.
3. Mirror the merged work into local `main` and return the worktree to its starting state:

   ```bash
   git fetch origin main:main 2>/dev/null || true   # update local main if not currently checked out elsewhere
   git checkout "$STARTING_BRANCH"
   ```

   If `git fetch origin main:main` fails (because local main is checked out in another worktree, common in emdash setups), that's fine — origin/main is the source of truth and the next sprint will pick it up via `git fetch origin main`. Don't error on it.

4. Stop the loop. Exit cleanly.
5. The `/canopy:pm-autonomous-loop` wrapper, if it invoked us, will sleep until "keep going" or 24h timeout — see `pm-autonomous-loop.md`.

## State that persists across sprints

```
~/.canopy/pm/<project>/
├── context.md
├── learnings.md
├── autonomous.yaml
├── runs/
│   └── YYYY-MM-DD-<theme-slug>.md   ← cycle log + self-review verdicts
└── sent-emails/
    └── YYYY-MM-DD-<theme-slug>/
        ├── email.md
        └── screenshots/
            └── *.png
```

`<project>` is `basename` of the repo root (e.g. `ace-web`, `canopy`). Resolve via `$CANOPY_PM_DIR` (set in Phase 0 step 1). `sent-emails/` exists so future sprints can avoid repeating "we shipped X" claims and so the user has a browseable archive of what's been said in their voice.
