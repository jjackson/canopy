---
description: Execute demo walkthroughs, run product improvement loops, adversarial reviews, and eval tracking. Use when asked to "run the walkthrough", "demo prep", "walkthrough improve", "walkthrough adversarial", "walkthrough eval", or "walkthrough <name>".
argument-hint: [<spec-name>|improve <name>|adversarial <name>|eval <name>|generate]
allowed-tools: [Read, Bash, Write, Edit, Glob, Grep, AskUserQuestion, Agent, Skill]
---

# Walkthrough

Execute demo walkthroughs, improve products, and generate stakeholder-ready presentations.

## Arguments

- `<spec-name>` — Execute a walkthrough spec from `docs/walkthroughs/<spec-name>.yaml`
- `improve <spec-name>` — Run, score, auto-fix failing dimensions, rerun until 4+/5
- `adversarial <spec-name>` — After passing at 4+, adversarial review to find embarrassments
- `eval <spec-name> [--update-baseline|--history|--compare <r1> <r2>]` — Run eval suite
- `generate` — Interactively create a new walkthrough spec
- No args: list available walkthrough specs in `docs/walkthroughs/`

## Routing

This command routes to either the **skill** (core run procedure) or the
**agent** (orchestrated improvement cycles) depending on the mode.

### Skill modes: `<name>`, `generate`, no args

These are deterministic pipelines that don't need orchestration.

Read the walkthrough SKILL.md and follow it step by step:

```bash
# Read the install path from installed_plugins.json (single source of truth)
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/walkthrough/SKILL.md')"
```

Read that file with the Read tool and follow it. The SKILL.md contains:
- Setup instructions (browse binary, state file, output directories)
- Authentication handling
- The mandatory 5-dimension scoring rubric
- The blocking rule (score ≤ 2 = stop immediately)
- The JSON data format and generator script invocation
- Generate mode instructions

**Do NOT improvise the walkthrough flow from memory.** The SKILL.md is the
authoritative source.

### Agent modes: `improve`, `adversarial`, `eval`

These require multi-step orchestration with persistent memory.

Read the walkthrough agent definition and follow it:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/agents/walkthrough.md')"
```

Read that file with the Read tool and follow it. The agent handles:
- **improve**: Run → analyze scores → dispatch specialist skills → rerun → iterate
- **adversarial**: Run → parallel code + live adversarial passes → incorporate findings
- **eval**: Run → score → compare to baseline → track history
