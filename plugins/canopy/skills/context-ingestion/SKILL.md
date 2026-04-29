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

### Step 2.5: Nugget Mining (required)

The single biggest determinant of whether a website looks smart at depth is
whether the team's *internal* operational lore made it onto the public site.
Most teams have years of Confluence pages, retrospectives, slack threads,
program-officer-readout decks, and post-mortems containing surprising,
specific, hard-won claims that never reach the marketing site. This step's
job is to actively mine that pile and surface candidate nuggets to the IA
step that comes next.

**A nugget is a single sentence (or a sentence pair) that is:**
1. **Specific** — names a number, mechanism, decision, or outcome that
   could not appear on a competitor's site verbatim.
2. **Surprising** — runs against conventional funder wisdom, or reveals
   something the team learned the hard way, or names a failure honestly.
3. **Publishable** — does not require disclosing donor-private data,
   personally identifying information, partner-confidential details, or
   in-progress work the team is not ready to claim.

**For every internal source you read in Step 2** (Confluence pages,
internal Drive docs, retro notes, post-mortems, narrative reports), scan
specifically for nuggets. Look for:

- "We were surprised that…" / "It turned out that…" / "Contrary to…"
- "We thought X. We tried it. It didn't work because…"
- Adversarial tests, paid red-teams, deliberate attempts to break
  the team's own systems
- Specific cost-per-outcome breakdowns (not cost-per-activity)
- Named failure modes: "In country X both LLOs dropped out because…"
- Methodology footnotes that reveal rigor (ground-truth comparisons,
  power calculations, instrument validation)
- Reframed metrics where the team chose a harder number to report
  ("we measure verified-visit cost not enrolled-FLW cost because…")

**Score each candidate nugget on two axes (1–5 each):**

- **Surprise** — would a foundation officer reading hundreds of decks
  have already heard this from a peer org? 1 = totally generic; 5 = I have
  never seen another org claim this.
- **Publishability** — given typical donor and partner contracts, can this
  appear on a public marketing site without redaction or approval? 1 = no
  way (donor-confidential, identifies a specific FLW, partner-private);
  5 = already in a public blog post or conference talk.

**Drop any nugget scoring below 3 on either axis.** A surprising-but-not-
publishable claim belongs in a foundation deck, not a public page; a
publishable-but-not-surprising claim is just marketing copy.

**Save survivors to `./context/nuggets.md`** in this exact format:

```markdown
# Nugget Candidates

Mined from internal sources. Each entry is a candidate for inclusion on a
depth page (program detail, LDVP step, /insights). The information-
architecture step routes them to specific pages and the website-builder's
depth-sharpness eval scores whether they actually landed.

## N1: [One-sentence claim]

**Source:** [File / page / doc + section, with internal link]
**Scope:** [Program name, or "Platform" if cross-program / mechanism evidence]
**Surprise:** N/5 — [one-line reason]
**Publishability:** N/5 — [one-line reason: any redactions needed? approvals required?]
**Suggested home:** [Which page(s) this might land on, and the named-example framing if cross-routed]
**Verbatim phrasing candidate:** "[A 1-2 sentence version that could appear on the site as-is — this is what the depth-sharpness judge will encounter]"
**Caveats / what's still unproven:** [Optional. If included, this is the hook for the page's Open Questions block.]
```

**Aim for 15–25 candidate nuggets across all internal sources.** The IA
step will winnow further; over-mining here is fine. Under-mining (e.g.,
4–5 generic candidates) means depth pages will fall back on marketing copy
and the depth-sharpness eval will score 3–5.

**Internal-only source attribution:** Internal sources cited in
`nuggets.md` use internal links (Drive, Confluence). The IA step is
responsible for translating any nugget that survives onto a public page
without exposing internal hrefs. Keep the internal links here — they're
the audit trail for future skeptical readers asking "where did this come
from?"

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
  },
  "nuggets_mined": {
    "candidates_total": 22,
    "after_threshold": 17,
    "median_surprise": 4,
    "median_publishability": 4,
    "path": "./context/nuggets.md"
  }
}
```

### Step 4: Report

Print a summary:
- How many programs found, how many with full content
- Content gaps (what's blocked by shortcuts, permissions, etc.)
- Classification breakdown (public vs internal items)
- **Nugget mining results**: total candidates, kept after threshold, median
  surprise + publishability scores, and the top 3 nuggets verbatim with
  their suggested homes (so the user gets immediate signal on whether the
  internal pile yielded smart content or generic marketing material)
- Recommendation: what to do next (e.g., "Run /canopy:information-architecture
  to route nuggets to pages, then /canopy:website-builder generate")

**If fewer than 8 nuggets survived the threshold**, surface a warning: the
depth-sharpness eval will likely score below 6 because the supply of smart
content is thin. Either lower the threshold (review dropped candidates),
mine additional internal sources, or ask the team for a brief on
unpublished learnings before proceeding to generation.
