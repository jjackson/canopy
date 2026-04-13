---
name: information-architecture
description: |
  Design the sitemap, navigation structure, and page templates for a website
  before generation. Maps content from ./context/ to specific pages and sections.
  Produces an IA document that the website-builder uses as its blueprint.
  Use after context-ingestion and before website generation.
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
---

# Information Architecture

Design the website structure before generating any HTML.

## When to Use

After content ingestion (./context/ exists), before website generation.
This step ensures the generator knows exactly what pages to create, what
content goes where, and how navigation works.

## Process

### Step 1: Inventory Available Content

Read `./context/manifest.json` and all content files. Build a picture of:
- What programs exist and which have enough content for full pages
- What media assets are available (videos, images, decks)
- What brand guidelines constrain the design
- What messaging/copy is approved

### Step 2: Define Site Structure

Based on the content inventory, propose a sitemap. Default structure:

```
/                        Homepage
/learn                   How It Works: Learn
/deliver                 How It Works: Deliver
/verify                  How It Works: Verify
/pay                     How It Works: Pay
/programs                Programs catalog (all programs)
/programs/<slug>         Program detail page (only for programs with full content)
```

For each page, define:
- **Template type**: homepage, ldvp-step, program-catalog, program-detail
- **Required sections**: what content sections appear on the page
- **Content mapping**: which context files feed which sections
- **Media placement**: where videos, images, or embeds go
- **Navigation**: how users get to/from this page

Adjust the sitemap based on available content. If a program doesn't have
enough content for a full page, it appears only in the catalog with a
"coming soon" indicator.

### Step 3: Define Navigation

Propose the nav structure:
- Primary nav items (max 5-6)
- Dropdown groupings (e.g., "How It Works" → Learn/Deliver/Verify/Pay)
- Mobile nav behavior (hamburger, slide-in, full-screen overlay)
- Breadcrumb patterns for sub-pages
- Footer link groups

### Step 4: Define Page Templates

For each template type, specify:

**Homepage:**
- Hero (tagline, pitch, CTA)
- How It Works (4-step LDVP summary)
- Programs showcase (card grid linking to catalog/detail pages)
- Impact stats
- Audience value props (Funders, LLOs, Workers)
- CTA / contact
- Footer

**LDVP Step Page:**
- Hero (step name, description)
- Key features (3 cards/blocks)
- Detail content (what workers do, how it works)
- Impact highlight (dark section with stat)
- Next step CTA (sequential link to next LDVP page)

**Program Catalog:**
- Hero (title, subtitle)
- Program grid/list (all programs with metadata)
- Programs with full pages → link to detail; others → "coming soon"

**Program Detail:**
- Hero (program name, one-line description)
- Key metrics row
- The Challenge section
- The Approach / Solution section
- How Connect Enables It (4 blocks)
- Program Details (table: regions, sector, funder, partners)
- Resources (public links only)
- CTA (back to catalog, request demo)

### Step 5: Write IA Document

Save to `./context/information-architecture.md`:

```markdown
# Information Architecture — [Site Name]

## Sitemap

| Page | Path | Template | Content Source | Status |
|------|------|----------|---------------|--------|
| Homepage | / | homepage | brand/messaging.md, programs/_index.md | Ready |
| Learn | /learn | ldvp-step | pages/learn.md | Ready |
| ... | ... | ... | ... | ... |
| KMC | /programs/kmc | program-detail | programs/kmc/ | Ready |
| Readers | /programs/readers | program-detail | programs/readers/ | Ready |

## Navigation

### Primary Nav
- Logo (left, links to /)
- How It Works → dropdown: Learn, Deliver, Verify, Pay
- Programs → /programs
- Impact → /#impact or /impact
- "Request a Demo" CTA (right)

### Mobile Nav
[Describe mobile behavior]

### Breadcrumbs
- Program pages: Programs > [Program Name]
- LDVP pages: How It Works > [Step Name]

### Footer
[Column layout and link groups]

## Page Templates
[Detailed section specs for each template type]

## Content Mapping
[Which context files feed which page sections]

## Media Placement
[Where public videos, images go — with actual URLs]

## Content Gaps
[What's missing and how to handle: placeholder text, "coming soon", omit]
```

### Step 6: User Review

Present the IA document to the user for approval. Key questions:
- Does the sitemap cover everything needed?
- Is the navigation intuitive?
- Are programs with "coming soon" handled appropriately?
- Any pages to add or remove?

Only proceed to generation after user approval.
