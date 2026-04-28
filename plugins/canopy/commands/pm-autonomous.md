---
description: Run one autonomous PM sprint — scout, draft email, ship, send-and-stop. Requires .claude/pm/autonomous.yaml.
allowed-tools: [Read, Glob, Grep, Bash, Agent, Write, Edit]
---

# /canopy:pm-autonomous

Run a SINGLE autonomous product-management sprint on the current project.

This command does NOT prompt for per-proposal approval — it auto-approves its own work, runs a multi-layer convince-self-it's-clean gate before each PR, and ends with a working-backwards release-notes email sent to the address configured in `.claude/pm/autonomous.yaml`.

The existing human-gated `/canopy:pm-scout` is the right command if you want per-proposal control.

## Process

1. Resolve the plugin install path:

   ```bash
   PLUGIN_PATH=$(python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'])")
   ```

2. Read the autonomous templates IN ORDER:
   - `$PLUGIN_PATH/skills/product-management/templates/autonomous/config-schema.md`
   - `$PLUGIN_PATH/skills/product-management/templates/autonomous/cycle.md`
   - `$PLUGIN_PATH/skills/product-management/templates/autonomous/convince-self-gate.md`
   - `$PLUGIN_PATH/skills/product-management/templates/autonomous/email-format.md`

3. Invoke the `canopy:product-management` skill (Skill tool) so its preamble runs.

4. Execute the autonomous cycle in `cycle.md` — Phase 0 first (validates config; refuses to run if invalid), then A → B → C → D → E.

5. Exit when Phase E sends the email (or the stuck-state email).

## Failure modes (none of these are bugs)

- Config invalid → Phase 0 prints the validator errors, refuses to run. Fix `.claude/pm/autonomous.yaml` and try again.
- No `.claude/pm/context.md` → bootstrap interactively first (the human-gated bootstrap flow still applies), then re-run.
- Phase A can't converge on an impressive email after deep scouting → sends a one-paragraph "no release notes this time" email and stops.
- Convince-self gate drops every candidate proposal → same as above.
- Post-deploy health stays red after `guardrails.max_fix_forward_attempts` cycles → "stuck" email, stop.

These are all features. The whole point is to refuse to ship weak content.
