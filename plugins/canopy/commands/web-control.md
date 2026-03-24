---
description: Connect to the user's Chrome browser via CDP to take screenshots and read page content. Does NOT launch a new browser.
argument-hint: [status|screenshot|content|enable]
allowed-tools: [Read, Bash]
---

# Web Control

Connect to the user's running Chrome via CDP (Chrome DevTools Protocol).

## Arguments

- `status` — check if CDP is active
- `screenshot [INDEX|--url URL]` — screenshot a tab
- `content [INDEX|--url URL]` — get text content
- `enable` — enable CDP on Chrome (restarts with debugging port)
- No args: run status

## Process

1. Invoke the `web-control` skill
2. Locate the canopy repo's `scripts/web-control.py`
3. Run the requested subcommand
4. For screenshots: read the output image with the Read tool to display it
