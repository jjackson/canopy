# Convince-self-it's-clean gate

Runs before each PR opens during a `/canopy:pm-autonomous` sprint. Goal: not just "tests pass" but "I'd defend this in a code review." Layered, in order. Any layer failing means the proposal is dropped (logged in the cycle log under `self-review-blocked`) and the loop moves on to re-derive the corresponding email highlight.

Don't skip layers. Don't merge them. The point of the gate is to make a different kind of mistake visible at each stage.

## 3a. Mechanical checks

Run all of these against the staged change. They are CHEAP — run them in parallel where possible.

1. `testing.unit` — must exit 0
2. `testing.lint` — must exit 0
3. `testing.types` — must exit 0
4. **Secret-leak scan (hardcoded patterns; not configurable):**

   ```bash
   git diff --staged | python3 "$PLUGIN_PATH/skills/product-management/scripts/secret_scan.py" --env-file .env
   ```

   Where `$PLUGIN_PATH` is resolved via `installed_plugins.json` as in `config-schema.md`. The `--env-file` flag is omitted if `.env` does not exist.

5. **Diff-size cap:**

   ```bash
   git diff --staged --stat | python3 "$PLUGIN_PATH/skills/product-management/scripts/diff_size_check.py" --limit "$DIFF_LIMIT"
   ```

   Where `$DIFF_LIMIT` is `guardrails.diff_size_limit_lines` from `autonomous.yaml`.

If any mechanical check fails, abandon this proposal — log it in the run log, do NOT try to "fix" by reducing scope. The cycle simply re-derives the email highlight.

## 3b. Self-review pass — five questions, written to the cycle log

Re-read the diff. Answer each question IN WRITING in the cycle log. The act of writing the answer is the gate — vague or evasive answers fail.

1. **What invariant did I just change?** Name a specific contract — input format, return semantics, side-effect ordering, persisted-state shape. Answer "none" or "I don't know" → FAIL.
2. **What's the riskiest line in this diff?** Quote a specific line. "Nothing is risky" on any non-trivial change → FAIL.
3. **What would a senior eng object to in code review?** Name a concrete objection, even if you disagree with it. "Nothing comes to mind" on a non-trivial change → FAIL (probable blind spot).
4. **Did I touch a test that codifies a behavior I'm changing?** If yes, did I update the test's *intent* or merely patch its assertions to match? "Patched the assertions" → FAIL.
5. **Would I be comfortable if this shipped while I was on vacation?** Hesitation → FAIL.

A failure on any question DROPS the proposal — write the question number and a one-sentence reason in the run log under `self-review-blocked`, then re-derive the corresponding email highlight (see Phase C in `cycle.md`).

## 3c. Dogfood pass — required for any "Try it" feature

For any change that's named in a `Try it:` line of the target email:

1. Start the local stack: `bash -lc "$(yq '.testing.dogfood.start_command' "$CANOPY_PM_DIR/autonomous.yaml")"`
2. Wait until `testing.dogfood.wait_for` returns 200, polling every 5s with a 5-min ceiling
3. Drive the change in the configured `headless_browser_skill` — actually click through, verify the expected behavior visibly happens
4. Capture a sequence of screenshots: a "before" (revert briefly OR feature-flag OR describe-from-memory if no clean before-state exists) and an "after". Save under `$CANOPY_PM_DIR/sent-emails/<sprint-slug>/screenshots/`
5. Reference them in the email body per `email-format.md`

A purely backend change (no user-visible surface) can SKIP dogfood, but then it CANNOT appear as a "Try it" highlight — only in the internal `*` section.

## 3d. Post-deploy health check

After deploy:

1. Poll each `shipping.post_deploy_health` URL with backoff (5s, 10s, 20s, 40s, 80s — total ~5 min) for 200 OK
2. If any URL fails or stays 5xx: do NOT auto-revert. The broken-prod state becomes the next scout finding; switch into a fix-forward investigation cycle (still autonomous)
3. If still red after `guardrails.max_fix_forward_attempts` cycles: log "stuck" in the run log, send a minimal "no email this sprint, here's why" note via `email.sender_skill`, stop.
