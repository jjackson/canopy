---
description: Execute a demo walkthrough against a live app and generate a stakeholder-ready HTML slideshow with screenshots, AI quality scores, and run-to-run comparison. Also runs product improvement loops and adversarial reviews. Use when asked to "run the walkthrough", "demo prep", "walkthrough improve", "walkthrough adversarial", or "walkthrough <name>".
argument-hint: [<spec-name>|improve <name>|adversarial <name>|generate]
allowed-tools: [Read, Bash, Write, Edit, Glob, Grep, AskUserQuestion, Agent, Skill]
---

# Walkthrough

Execute demo walkthroughs, improve products, and generate stakeholder-ready presentations.

## Arguments

- `<spec-name>` — Execute a walkthrough spec from `docs/walkthroughs/<spec-name>.yaml`
- `improve <spec-name>` — Run, score, auto-fix failing dimensions via gstack skills, rerun
- `adversarial <spec-name>` — After passing at 4+, adversarial review to find embarrassments
- `generate` — Interactively create a new walkthrough spec
- No args: list available walkthrough specs in `docs/walkthroughs/`

## CRITICAL: Read the full skill instructions

You MUST read the walkthrough SKILL.md before doing anything else. Find it:

```bash
# Find the latest version in the plugin cache
ls -d ~/.claude/plugins/cache/canopy/canopy/*/skills/walkthrough/SKILL.md 2>/dev/null | sort -V | tail -1
```

Read that file with the Read tool and follow it **step by step**. The SKILL.md contains:
- Setup instructions (browse binary, state file, output directories)
- Authentication handling
- The mandatory 5-dimension scoring rubric (Content, App Page, Screenshot, Slide, Demo Readiness)
- The blocking rule (score ≤ 2 = stop immediately)
- The prioritized action list format
- The JSON data format and generator script invocation
- Improve mode, adversarial mode, and generate mode instructions

**Do NOT improvise the walkthrough flow from memory.** The SKILL.md is the authoritative
source. If you skip reading it, you will miss critical steps like generating the HTML
deck, using the scoring rubric, and running the generator script.
