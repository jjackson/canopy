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

## Process

1. Invoke the `walkthrough` skill
2. Follow the execution flow for the selected mode
