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

## Process

For `ingest`:
1. Invoke the `context-ingestion` skill
2. Follow its process to discover MCP sources and pull content into ./context/

For `ia`:
1. Check that ./context/ exists (suggest running `ingest` first if not)
2. Invoke the `information-architecture` skill
3. Follow its process to design the sitemap and write ./context/information-architecture.md
4. Get user approval on the IA before proceeding

For `generate`:
1. Check if ./context/ exists. If not, suggest running `ingest` first.
2. Check if ./context/information-architecture.md exists. If not, suggest running `ia` first.
3. If running as the `website-builder` agent (has memory), follow the agent's generate pipeline,
   using the IA document as the blueprint for what pages to create and what content goes where.
4. If running as a skill (no agent memory), read ./context/ and the IA document directly,
   then run the pipeline inline.

For `eval`:
1. Invoke the `website-builder` skill
2. Follow the eval workflow for the specified product
