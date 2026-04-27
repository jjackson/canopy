---
description: >
  Build marketing websites from product context, or run evaluation suites
  to measure and improve generation quality. Uses persistent memory for
  brand context. Use when asked to "build a website", "generate a page",
  "eval website", or "website-builder".
argument-hint: [generate|ingest|ia|eval <product>|eval <product> --update-baseline|eval <product> --history|eval <product> --compare <run1> <run2>]
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion, Agent, Skill]
---

# Website Builder

Build marketing websites from product context or evaluate generation quality.

## Arguments

- `ingest` — Run context ingestion: pull content from MCP sources (Drive, Confluence) into ./context/
- `ia` — Run information architecture: design sitemap, nav, and page templates from ./context/
- `generate` (default) — Run the full generation pipeline using ./context/ and IA blueprint
- `eval <product>` — Run eval suite against fixed context in evals/<product>/
- `eval <product> --update-baseline` — Set most recent run as baseline
- `eval <product> --history` — Show score trends
- `eval <product> --compare <run1> <run2>` — Compare two runs
- No args: same as `generate`

## Routing

First, resolve the canopy install path once:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'])"
```

Then read the SKILL.md for the requested mode and follow it step by step. **Do NOT improvise from memory.** The SKILL.md is the authoritative source.

- `ingest` → `<installPath>/skills/context-ingestion/SKILL.md`
- `ia` → `<installPath>/skills/information-architecture/SKILL.md` (after confirming `./context/` exists)
- `generate` (or no args) → `<installPath>/skills/website-builder/SKILL.md` (after confirming `./context/` and `./context/information-architecture.md` exist)
- `eval <product> [...flags]` → `<installPath>/skills/website-builder/SKILL.md`, eval workflow

If running as the `website-builder` agent (has memory), follow the agent's generate pipeline instead of the skill for the `generate` mode, using the IA document as the blueprint.
