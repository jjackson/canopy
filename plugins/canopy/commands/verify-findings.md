---
description: Re-verify session-review findings against current state of their target repos. Drops findings whose fix already shipped. Use before acting on findings or after a long pause between review and implementation.
argument-hint: [<proposal-id-prefix>...|--all-pending]
allowed-tools: [Read, Bash, Write, Edit, Glob, Grep, Skill]
---

# Verify Findings

Re-check the listed proposals (or all pending) against the current
state of their target repos. Flags ones that have already shipped
so you don't implement work that's already done.

## Arguments

- `<proposal-id-prefix>...` — one or more 8+ character proposal-id
  prefixes (matches `~/.claude/canopy/proposals/<prefix>*.yaml`).
  Multiple prefixes can be space-separated.
- `--all-pending` — verify every proposal whose status is currently
  `pending`. Default if no other arg is provided.

## Examples

- `/canopy:verify-findings 85cbef676ae2 fb1f7de7b083` — verify two
  specific proposals
- `/canopy:verify-findings --all-pending` — verify every pending
  proposal in the canopy state directory
- `/canopy:verify-findings` — same as `--all-pending`

## Process

Read the verify-findings SKILL.md from disk and follow it:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/verify-findings/SKILL.md')"
```

Read that file with the Read tool and follow it step by step, passing
the user's argument(s) (if any) to the skill. **Do NOT improvise from
memory.** The SKILL.md is the authoritative source — its triage table
and evidence-citation rules are load-bearing.
