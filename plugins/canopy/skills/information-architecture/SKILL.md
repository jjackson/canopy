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

### Step 4z: Foundation Judge — Harsh Review

After insights are extracted and before they're routed to pages, run a **harsh
judge pass**. Imagine a specific reader: a program officer at a large
foundation (Gates, GiveWell, CIFF, Founders Pledge) evaluating a $10M+ grant.
They've read hundreds of pitches. They've seen every "empower communities"
marketing site. They're looking for reasons to say no.

**The judge has three possible verdicts for each insight:**

1. **Keep as-is** — the insight passes every check, scope is accurate, evidence is sound.
2. **Rewrite** — the underlying finding is real and worth including, but the framing, scope, numbers, or "why this is hard" context need work.
3. **Drop** — the insight should not appear on the site at all. A weak, misframed, or misattributed insight is worse than no insight. Do not try to improve something that shouldn't ship.

**When to drop an insight (not rewrite):**
- It's actually just a fact or marketing claim dressed up as a learning — there's no real "before / after," nothing changed.
- Its strongest form is still generic and couldn't survive a "so what?" from a skeptical reader.
- The evidence base is too thin (e.g., one anecdote, a single small-N study with no planned follow-up).
- The scope cannot be fixed: the source material is ambiguous about what's a program result vs a platform claim, and no amount of reframing resolves it without new evidence.
- It duplicates a stronger insight with no new dimension.
- Including it would require overclaiming (attributing a program's result to the platform) in order to be interesting.

Drop decisions matter. A site with 6 sharp insights outperforms a site with 10 where 4 are weak or overreaching. Log drops in `./context/insights-dropped.md` with the insight, the reason, and whether it could be revived later with better evidence.

For each kept or rewritten insight, check:

**1. Is the scale number the *systemic* number or a pilot number?**
A pilot of 76 FLWs in one country is a methodology footnote. The systemic
truth — 5,000+ FLWs across 12 countries delivering 1M+ visits — is the
headline. Never lead with pilot numbers when program-scale numbers exist.

**2. Does every significant number have a benchmark?**
"94% coverage" — vs what? "880,000 visits" — worth how much? Relative to
what market? Numbers without benchmarks fail the "so what?" test.

**3. Are small-N studies framed with sensitivity/power context?**
A 50-caregiver survey or 20-interview qualitative study is fine, but needs
framing: "qualitative findings (n=20); RCT with [partner] underway" or
"power sufficient to detect X% change at 80% confidence." Otherwise a
hardened reader will note the sample as a weakness.

**4. Are satisfaction/self-report metrics distinguished from impact metrics?**
"9.5/10 satisfaction from LLOs" is sticky upward and measures happiness,
not impact. Replace with performance signals: "7/7 LLOs completed campaigns
vs X% industry baseline."

**5. Does the "why this is hard" framing earn the claim?**
Why is 94% coverage impressive? (Traditional campaigns plateau at 82%.
Measured against GRID3 gold-standard population estimates.) Why is the
Trial Run model insightful? (Conventional funder wisdom was pre-vetting;
we proved it doesn't predict performance.) Without the hard-fought context,
claims land as ordinary.

**6. Are we being defensive where we should be confident?**
"We are piloting" where we mean "live across 12 countries." "Early results
suggest" where multi-year data exists. "~400 FLWs" where precision exists.
The squiggle tilde signals uncertainty — remove it when you have real numbers.

**7. Are squiggles (~) and vague descriptors hiding real data?**
"~100 applications" reads as "we didn't track." "37 LLOs (from 107
applications based on governance maturity, geographic need, health systems
alignment)" reads as rigorous.

**8. Does each insight own its failure mode honestly?**
A foundation officer looks for willingness to name what didn't work — not
as weakness but as credibility. "In CAR both LLOs dropped out; we now
require in-country presence in fragile contexts" is stronger than silence.

**9. Is the scope accurate? Is a program-specific result being passed off as a platform claim?**
A program result is evidence for that program. It is not evidence that the platform produces the same result everywhere. If an insight's `Scope:` is "Platform" but the supporting data comes from one program, the scope is wrong — either rescope it to the program (and reframe for LDVP/audience pages as a named example), or drop it. A diligence reader reading "Connect reduces delivery cost 22%" and then finding the supporting data is from a single CHC cohort will discount every other claim on the page. Overclaiming poisons credible claims nearby.

Specifically watch for:
- A single program's stat (cost, completion, detection, satisfaction, coverage) stated as a Connect-wide fact.
- "Connect does X" where the evidence is actually "in program P, Connect did X."
- Platform-level claims that cite a single program's report as the only source.
- LDVP / audience-page copy that strips the program name from a program-scoped insight.

Verdict: Rewrite (reframe with scope + named example) or Drop (if the cross-program evidence doesn't exist and won't soon).

**For each insight, decide Keep / Rewrite / Drop and act on the verdict.**

**Rewrites** apply the principle that what impresses a foundation is not the marketing polish, it's the specificity and the willingness to show your work. Aim for:
- Scope: accurate and named — "In the CHC program…" not "Connect…"
- Scale: always cite systemic numbers, reserve pilot numbers for methodology
- Benchmark: every claim comparable to a known baseline
- Precision: real numbers, no squiggles
- Honesty: name what's unproven or still underway
- Asymmetry: cost per outcome, not cost per activity

**Drops** are recorded with their reason in `./context/insights-dropped.md`.

Save the kept and rewritten insights back to `./context/insights.md`. They are now foundation-ready and routable to pages.

### Step 4a: Insight Extraction (DO THIS BEFORE ROUTING)

**This step is the difference between a skeletal site and an impressive one.**

Facts are not insights. "AUC 0.91" is a fact. "We paid people bonuses to defeat
our fraud detection and they still couldn't" is an insight. A site full of
facts reads like a marketing page. A site full of insights reads like you're
getting inside knowledge from a team that knows what it's doing.

Before routing content to pages, read through every source report and extract
the genuine **learnings** — the moments where the team figured something out,
changed approach, or surfaced a counterintuitive finding. Save these to
`./context/insights.md`.

**What qualifies as an insight (all four should be true):**
1. **There's a "before" and an "after"** — something was thought, tried, or assumed; something was learned; something changed as a result
2. **It's specific to *this* team's work** — it couldn't appear on a competitor's site verbatim
3. **It demonstrates methodological sophistication** — shows rigor, honesty, or hard-won judgment
4. **A practitioner would find it interesting** — not just marketing language, but something worth their time

**What DOESN'T qualify (even if dressed up):**
- Generic claims ("data-driven," "evidence-based," "scalable")
- Aspirational statements about impact
- Quotes from mission statements
- Numbers without tension (e.g., "100,000 visits delivered" — impressive scale, but no insight unless paired with what it proves)

**Scope every insight to its origin. Do not generalize.**

An insight extracted from a specific program's report is a *program-level* insight — not a platform-wide claim. Tag each insight to its source context and keep the claim scoped to that context.

- **Good:** "In the CHC program, Connect got leaner as it scaled — 22% cost reduction per delivery between year 1 and year 2." Scoped to CHC. Can run on the CHC page confidently. Can appear on a platform/LDVP page only as a named example ("For example, in CHC…"), not as a Connect-wide claim.
- **Bad:** "Connect reduces delivery costs by 22% as it scales." This misattributes one program's result to the whole platform. A diligence reader will spot it and lose trust.

Rules:
- A program's stat (cost, completion rate, detection rate, satisfaction, coverage) stays scoped to that program unless multiple programs *independently* produced the same result **and** the underlying mechanism is platform-level.
- Platform-level claims require evidence drawn from across programs ("across N programs in M countries…") or from a platform mechanism that is the same code path regardless of program (e.g., fraud detection logic).
- When in doubt, scope it down. A well-scoped specific claim is stronger than a loosely-scoped general one.
- Scoping must survive routing (Step 4b): when an insight is routed to an LDVP page or audience page, it must be reframed as a named example — never stripped of its origin.
- In the insight structure below, the `Scope:` field is mandatory.

**Insight structure (use this exact shape):**

```markdown
## Insight N: [Short, specific claim]

**Scope:** [Program name, or "Platform" if drawn from cross-program / mechanism evidence. Required — do not leave blank.]

**What we thought:** [The prior assumption or standard approach]

**What we learned:** [The finding — specific, often surprising or counterintuitive]

**What we changed:** [The resulting change — a new model, a new mechanism, a new policy]

**Why it matters:** [The implication — what this enables, what it prevents, or what it reveals]

**What didn't work / honest caveats:** [Optional, but powerful when present]

**Home:** [Which pages get this insight, and how each frames it differently. For scope=Program insights appearing on LDVP/audience pages, specify the named-example framing: "Pay page: framed as 'In CHC, Connect got leaner as it scaled…'"]
```

**Where to look for insights in source material:**
- Sentences containing: "we found," "we learned," "it turned out," "contrary to," "despite," "however," "we realized," "we assumed"
- Sections labeled: Learnings, Retrospective, Lessons, Limitations, What Didn't Work
- Places where the team describes why something is different from the standard approach
- Places where a failure or limitation is named explicitly
- Methodological details that reveal rigor (e.g., adversarial testing, iterative experiments)

**Aim for 8-12 insights for a multi-page site.** Fewer, and the site will feel
thin. More, and individual insights lose their weight.

**Then and only then, route them.**

### Step 4b: Content Routing

Once insights are extracted, map them to pages. Insights from reports,
learnings, and program data often belong on **multiple pages simultaneously**.
A single insight can be evidence for:
- A **program page** (proving the specific intervention works)
- A **platform/mechanism page** (proving the LDVP step works in general)
- An **audience page** (proving value for funders, LLOs, or workers)

For every insight, create a routing entry:

```markdown
## Content Routing Table

| Insight | Scope | Source | Program Page | LDVP Page (as named example) | Audience Page (as named example) |
|---------|-------|--------|-------------|------------------------------|----------------------------------|
| LLO performance can't be pre-vetted; invented Trial Run model | CHC | FP report | CHC | Deliver ("In CHC…") | Funders ("In CHC…") |
| Workers cluster; microplans force outward (0.4→1.4 visits/child) | CHC | FP report | CHC | Verify ("In CHC…") | Funders ("In CHC…") |
| Paid FLWs to defeat fraud detection; still detected 97.5% | Platform (mechanism is Connect fraud detection, tested in CHC) | FP report | CHC | Verify | Funders |
| CHC delivery cost fell 22% from year 1 to year 2 as scale grew | CHC | FP report | CHC | Pay ("In CHC…") | Funders ("In CHC…") |
| Knowledge ≠ competence; layered training with AI coach | ECD | ECD report | ECD | Learn ("In ECD…") | — |
```

**Rules:**
- Every insight gets at least one page assignment
- A program-scoped insight appearing on an LDVP or audience page must be reframed as a **named example** ("In the CHC program…"), not restated as a platform claim. Strip the program name and the claim becomes an overclaim.
- Platform-scoped insights (cross-program evidence, or a mechanism that is the same code path regardless of program) can appear on LDVP/audience pages without named-example framing.
- Program-specific implementation details go on program pages
- Cost/ROI/impact evidence can appear on audience pages, but keep scope intact — cite the program, don't promote the number to platform-wide.
- Don't duplicate long content — reference the same data differently on each page
  (e.g., the Learn page frames AI coaching as "how training works at scale"
  while the ECD page frames it as "what makes this program unique")

### Step 4b2: Learning Presentation Pattern (how to show each insight)

Once insights are extracted and routed, decide how each page will **present**
them. On a deep sub-page — program detail, LDVP step — the visitor has already
clicked in. They're not looking for a hook; they're looking for substance.

**The unit is not a "signature moment." It's a well-written case entry.**
Roughly 250-600 words per learning, with structure that rewards both skimming
and close reading.

Pick a presentation pattern for each page template. Different variants of the
same site can use different patterns on the same IA — one variant might use
Pattern A for LDVP pages, another variant might use Pattern D. The content
stays the same; the treatment changes.

#### Pattern A: Engineering Retrospective
Each learning gets structured sub-headings: **The question we had** → **What
we tried** → **What we found** → **What changed** → **What's still open**.
Like a really good engineering blog post. Data and specific examples live in
the prose, not floating in stat cards. Sources in small grey text at the
bottom of each learning. Best for: platform/mechanism pages (Verify, Deliver),
technical audiences, teams who want to show methodological rigor.

#### Pattern B: Two-Column Long-Form
Body text on the left (~60% width), a narrower right column for supporting
material: methodology notes, specific numbers, links to deeper reading, pull
quotes *drawn from the body*. Reads like a New Yorker piece, but with data.
Best for: narrative-heavy pages, program detail pages where the story matters
as much as the mechanism.

#### Pattern C: Annotated Discovery
The body reads as one piece of well-structured prose. Numbers and claims are
visually marked with a small superscript or underline — hover/click reveals
a source note, methodology detail, or caveat. Clean narrative surface,
research-paper depth underneath. Best for: pages with high-density evidence
where inline citations matter (Verify, detailed program pages).

#### Pattern D: Progression of Thinking
Treat the learning as a timeline: "In early 2025 we assumed X. Then we ran
the pilot. In Q2 the data suggested Y. By Q4 we had redesigned the
intervention." Each phase has its data and reasoning. Feels like watching a
team actually think. Best for: showing how a program evolved, learning pages,
case studies where iteration is part of the story.

#### Pattern E: Question-Led
Each learning is framed as a real question the team had to answer: *"How do
we vet LLOs when past reputation doesn't predict performance?"* Answer runs
300-500 words covering the approach, the data, and what's still unresolved.
Very readable, invites both skimming and close reading. Best for: program
detail pages where each program surfaces different questions, or audience
pages (funders, LLOs, workers) where each audience has different questions.

### Choosing patterns

For a three-variant site, pick three distinct pattern combinations. For example:
- **Variant 1:** Pattern A (Engineering Retrospective) for all LDVP + Pattern E (Question-Led) for program details
- **Variant 2:** Pattern B (Two-Column Long-Form) throughout
- **Variant 3:** Pattern D (Progression of Thinking) for LDVP + Pattern C (Annotated Discovery) for program details

Record your pattern choices per page in the IA document. The generator will
follow these as the treatment spec.

**Core principle:** detail, not one-liners. A visitor on a sub-page has already
committed. Reward the commitment with substance. 250-600 words per learning is
the right weight.

### Step 4c: Multi-Variant Design Direction

The generator should NOT lock in on a single approach. For each page template,
define 2-3 **design directions** that the generator can explore:

**Example directions for program detail pages:**
1. **Data-dashboard** — Lead with metrics, charts, key numbers. Clinical, credible.
2. **Case-study narrative** — Lead with the problem/challenge. Storytelling arc.
3. **Magazine editorial** — Lead with a bold visual statement. Pull quotes, large type.

**Example directions for LDVP pages:**
1. **Mechanism-first** — Explain how it works technically, then show evidence
2. **Evidence-first** — Lead with results/stats, then explain the mechanism
3. **Story-first** — Lead with a worker's journey, then generalize

Include these directions in the IA document so the generator can produce
multiple variants. The user should be able to see and compare approaches.

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

## Content Routing
[Insight → page mapping table. Each insight lists which pages it appears on
and how it's framed differently on each.]

## Design Directions
[For each page template, 2-3 variant approaches the generator should explore.
The user picks after seeing them, or mixes elements from multiple.]

## Learning Presentation Patterns
[For each variant × page-template, specify the learning presentation pattern
(A-E) to use. Detail not one-liners: 250-600 words per learning. Example:

| Variant | LDVP pages | Program detail pages |
|---------|-----------|---------------------|
| 1 | Pattern A (Engineering Retrospective) | Pattern E (Question-Led) |
| 2 | Pattern B (Two-Column Long-Form) | Pattern B (Two-Column Long-Form) |
| 3 | Pattern D (Progression of Thinking) | Pattern C (Annotated Discovery) |
]

## Content Mapping
[Which context files feed which page sections]

## Media Placement
[Where public videos, images go — with actual URLs.
Internal links (Drive, Confluence) must NOT appear as public hrefs.]

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
