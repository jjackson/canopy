---
description: Execute a demo walkthrough against a live app and generate a stakeholder-ready HTML slideshow with screenshots, AI quality scores, and run-to-run comparison. Use when asked to "run the walkthrough", "demo prep", "walkthrough generate", or "walkthrough <name>".
argument-hint: [<spec-name>|generate]
allowed-tools: [Read, Bash, Write, Edit, Glob, Grep, AskUserQuestion, Agent]
---

# Walkthrough

Execute demo walkthroughs and generate stakeholder-ready presentations.

## Arguments

- `<spec-name>` — Execute a walkthrough spec from `docs/walkthroughs/<spec-name>.yaml`
- `generate` — Interactively create a new walkthrough spec
- No args: list available walkthrough specs in `docs/walkthroughs/`

## Process

1. Invoke the `walkthrough` skill
2. Follow the execution flow: setup → authenticate → execute scenes → generate deck
