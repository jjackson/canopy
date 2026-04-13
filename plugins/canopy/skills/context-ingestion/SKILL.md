---
name: context-ingestion
description: |
  Pull product content from MCP sources (Google Drive, Confluence, etc.) into
  a structured ./context/ directory for website generation. Classifies content
  as public vs internal, inventories available assets, and produces a manifest.
  Use before website generation to gather all available content.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Agent
---

# Context Ingestion

Pull content from external sources into a structured local context directory
that the website-builder can consume.

## When to Use

Before running website generation, when content lives in external systems
(Google Drive, Confluence, etc.) rather than in a local ./context/ directory.

## Process

### Step 1: Discover Sources

Check for available MCP tools that provide content:

1. **Google Drive** — Look for `mcp__plugin_ace_ace-gdrive__*` tools
   - Check for a README or content index doc that lists folder structure
   - List program folders, content folders, media folders
2. **Confluence/Atlassian** — Look for `mcp__atlassian__*` tools
   - Search for marketing hubs, program pages, glossaries
3. **Local files** — Check for existing ./context/ directory with partial content

Report what sources are available before proceeding.

### Step 2: Pull Content

For each discovered source, extract content into `./context/`:

**Directory structure to create:**
```
./context/
  manifest.json          # What was pulled, from where, timestamps
  brand/
    guidelines.md        # Brand colors, fonts, logo specs
    messaging.md         # Tagline, elevator pitch, key terminology
  programs/
    _index.md            # List of all programs with metadata
    <program-slug>/
      overview.md        # Program description, regions, scale, funder
      content.md         # Detailed content (if readable)
      resources.md       # Available assets (videos, decks, photos)
  pages/
    homepage.md          # Content mapped to homepage sections
    learn.md             # LDVP step content
    deliver.md
    verify.md
    pay.md
  assets/
    inventory.md         # List of available media assets with sources
```

**Content classification rules:**
- Files/docs tagged `[Public]`, `[Blog]`, `[External]` → mark as public-safe
- Files tagged `[WIP]`, `[Internal]` → mark as internal-only
- Google Drive links → mark as internal (not for public website href)
- YouTube links → mark as public
- Confluence public spaces → public; internal spaces → internal

**Handling shortcuts:**
If Google Drive files are shortcuts (`application/vnd.google-apps.shortcut`),
attempt to read via the target ID (the MCP tool resolves shortcuts
automatically). If resolution fails, log them in the manifest as
`"status": "shortcut_unresolvable"` with the file name and shortcut ID.
Note what content would be available if resolved.

### Step 3: Build Manifest

Write `./context/manifest.json`:

```json
{
  "generated_at": "ISO_TIMESTAMP",
  "sources": [
    {
      "type": "google_drive",
      "folder_id": "...",
      "files_pulled": 12,
      "files_skipped": 3,
      "skip_reasons": ["shortcut_unresolvable", "permission_denied"]
    },
    {
      "type": "confluence",
      "space": "connect",
      "pages_pulled": 5
    }
  ],
  "programs": [
    {
      "slug": "kmc",
      "name": "Kangaroo Mother Care",
      "has_overview": true,
      "has_detailed_content": false,
      "has_resources": true,
      "content_gaps": ["Blog post blocked by shortcut", "Product showcase deck blocked"]
    }
  ],
  "content_classification": {
    "public": ["youtube_video_url", "program_descriptions"],
    "internal_only": ["drive_folder_links", "salesforce_links", "asana_links"]
  }
}
```

### Step 4: Report

Print a summary:
- How many programs found, how many with full content
- Content gaps (what's blocked by shortcuts, permissions, etc.)
- Classification breakdown (public vs internal items)
- Recommendation: what to do next (e.g., "Run /canopy:website-builder generate")
