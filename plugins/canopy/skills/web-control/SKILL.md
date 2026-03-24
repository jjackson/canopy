---
name: web-control
description: Connect to the user's running Chrome browser via CDP to see what they're working on — list tabs, take screenshots, read page content. Does NOT launch a new browser.
version: 0.1.0
---

# Web Control — Connect to the User's Chrome via CDP

Connect to the user's **actual running Chrome** browser via the Chrome DevTools
Protocol. This lets you see what the user is working on, take screenshots of
their tabs, and read page content — without launching a headless browser.

## When to Use

- User says "look at what I have open", "see my browser", "check my tab"
- You need to see a live site the user is actively developing
- You want visual context for what the user is describing
- Debugging a site the user has open with their auth session / cookies

## Prerequisites

Chrome must be running with `--remote-debugging-port`. The `enable` command
handles this automatically (gracefully restarts Chrome, preserving all tabs).

## Tool Location

The control script lives in the canopy repo:

```
CANOPY_REPO/scripts/web-control.py
```

Find it by locating the canopy repo (has `pyproject.toml` with `name = "canopy"`),
or check common locations:
- `~/emdash-projects/canopy-orchestrator/scripts/web-control.py`
- The repo where this skill is defined

**Requires:** `playwright` (`pip install playwright && playwright install chromium`)

## Commands

### 1. Enable CDP (first time or after Chrome restart)

```bash
python3 CANOPY_REPO/scripts/web-control.py enable
```

This runs `chrome-debug.sh` which:
- Checks if CDP is already active (does nothing if so)
- Saves all open tabs via AppleScript
- Gracefully quits Chrome
- Restarts with `--remote-debugging-port=9222`
- Restores all tabs

**Always run `status` first** — if CDP is already active, skip enable.

### 2. Check Status

```bash
python3 CANOPY_REPO/scripts/web-control.py status
```

Shows browser version and confirms CDP is reachable.

### 3. List Tabs

```bash
python3 CANOPY_REPO/scripts/web-control.py tabs
```

Shows all open tabs with index numbers and URLs. Use these indices
for screenshot and content commands.

### 4. Screenshot a Tab

```bash
# Screenshot the active tab (index 0)
python3 CANOPY_REPO/scripts/web-control.py screenshot

# Screenshot tab by index
python3 CANOPY_REPO/scripts/web-control.py screenshot 2

# Screenshot tab matching a URL
python3 CANOPY_REPO/scripts/web-control.py screenshot --url "localhost:3000"

# Viewport only (not full page)
python3 CANOPY_REPO/scripts/web-control.py screenshot --viewport-only

# Custom output path
python3 CANOPY_REPO/scripts/web-control.py screenshot -o /tmp/my-screenshot.png
```

Default output: `/tmp/web-control-screenshot.png`

After taking a screenshot, **read the image file** with the Read tool to see it.

### 5. Read Page Content

```bash
# Content of active tab
python3 CANOPY_REPO/scripts/web-control.py content

# Content of specific tab
python3 CANOPY_REPO/scripts/web-control.py content 1

# Content matching URL
python3 CANOPY_REPO/scripts/web-control.py content --url "github.com"
```

Returns the visible text content of the page (scripts/styles stripped).

## Typical Flow

```
1. status          → is CDP already active?
2. enable          → (only if status failed) restart Chrome with CDP
3. tabs            → see what's open
4. screenshot N    → capture what user is looking at
5. Read screenshot → view the image
6. content N       → get text if needed
```

## Important Notes

- This connects to the **user's real browser** with their cookies, logins, etc.
- Never close tabs or navigate away from the user's pages without asking
- Screenshots capture the actual rendered page including dynamic content
- The CDP connection is read-only by design — observe, don't modify
- Port 9222 is the default; pass `--port PORT` to use a different one
- If Chrome was already running without CDP, `enable` will restart it (saves/restores tabs)

## Difference from gstack browse

| | web-control | gstack browse |
|---|---|---|
| Browser | User's Chrome | Headless Chromium |
| Auth/cookies | User's real session | Fresh (or imported) |
| Purpose | See what user is working on | QA testing |
| Tabs | User's actual tabs | Controlled by Claude |
| Modifies browser | No (read-only) | Yes (full control) |
